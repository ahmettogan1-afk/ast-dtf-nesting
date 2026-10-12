import json
import math
import os
import shutil
import time
from pathlib import Path
import pymupdf as fitz
import pytest
from shapely.geometry import Polygon,Point,box
from shapely import affinity,wkt
from backend.geometry import SVGGeometry,reserve_holes
from backend.vector_io import ingest,export_pdf,export_svg,placed_geometry,PT
from backend.nesting import Packer
from backend.validation import validate


def pdf_logo(path,kind='white'):
    doc=fitz.open();p=doc.new_page(width=120*PT,height=90*PT)
    if kind=='white':p.draw_rect(fitz.Rect(10*PT,10*PT,50*PT,30*PT),color=None,fill=(1,1,1))
    if kind=='ring':p.draw_circle(fitz.Point(40*PT,40*PT),25*PT,color=(1,1,1),width=4*PT)
    if kind=='u':
        points=[(10,10),(20,10),(20,50),(50,50),(50,10),(60,10),(60,60),(10,60),(10,10)]
        sh=p.new_shape();sh.draw_polyline([fitz.Point(x*PT,y*PT) for x,y in points]);sh.finish(fill=(1,1,1),color=None);sh.commit()
    doc.save(path);doc.close()

def synthetic(g,aid='a',n=1,locked=True):
    x,y,xx,yy=g.bounds;g=affinity.translate(g,-x,-y)
    return {'id':aid,'name':aid,'geometry':g.wkt,'width':xx-x,'height':yy-y,'native_width':xx-x,'native_height':yy-y,'quantity':n,'rotation_locked':locked,'confirmed':True}

def job(assets,width=580,gap=3):
    return {'name':'Test','assets':list(assets.values()),'settings':{'width':width,'margin':5,'gap':gap,'mode':'maximum'},'best':[]}

def test_white_vector(tmp_path):
    f=tmp_path/'white.pdf';pdf_logo(f)
    a=ingest(f.read_bytes(),'white.pdf',tmp_path/'out')[0]
    assert a['vector_paths']>0 and not a['white_background']
    assert wkt.loads(a['geometry']).area>799
    p=fitz.open(tmp_path/'out'/a['pdf']);assert len(p[0].get_images())==0
    assert p[0].get_drawings()[0]['fill']==(1,1,1)

def test_hole_is_reserved():
    ring=Point(30,30).buffer(25).difference(Point(30,30).buffer(20))
    g=reserve_holes(ring);assert g.contains(Point(30,30))
    a=synthetic(g);b=synthetic(box(0,0,10,10),'b')
    assets={'a':a,'b':b};j=job(assets)
    p=[{'asset_id':'a','instance':'a:0','x':10,'y':10,'angle':0},{'asset_id':'b','instance':'b:0','x':30,'y':30,'angle':0}]
    assert not validate(j,assets,p)['valid']

def test_outer_concavity_used():
    u=Polygon([(0,0),(10,0),(10,40),(50,40),(50,0),(60,0),(60,50),(0,50)])
    assets={'a':synthetic(u),'b':synthetic(box(0,0,25,20),'b')}
    j=job(assets,width=80);p=Packer(assets,j['settings']).finish();r=validate(j,assets,p)
    assert r['valid'],r
    assert r['length']<61 # 20 mm small part fits inside OPEN U, not under it
    geoms=[placed_geometry(assets[x['asset_id']],x) for x in p]
    assert box(*geoms[0].bounds).intersection(box(*geoms[1].bounds)).area>100

def test_100_distinct_parts_gap():
    assets={str(i):synthetic(Polygon([(0,0),(12+i%8,0),(10+i%5,8+i%7),(0,10+i%3)]),str(i)) for i in range(100)}
    j=job(assets);p=Packer(assets,j['settings']).finish();r=validate(j,assets,p)
    assert r['valid'],r
    geoms=[placed_geometry(assets[x['asset_id']],x) for x in p]
    assert min(g.distance(h) for i,g in enumerate(geoms) for h in geoms[i+1:])>=3-1e-6

def test_arbitrary_rotation_preserves_area():
    a=synthetic(Polygon([(0,0),(40,0),(40,10),(10,30),(0,30)]),locked=False)
    area=wkt.loads(a['geometry']).area
    for angle in (7,13,24,43,87,126,218,337,.25):
        g=placed_geometry(a,{'angle':angle,'x':10,'y':20})
        assert g.area==pytest.approx(area,abs=1e-7)
    pack=Packer({'a':a},job({'a':a})['settings'],attempt=1)
    assert any(angle%90!=0 for angle in pack.angles('a'))

def test_quantity_37():
    assets={'a':synthetic(box(0,0,15,8),n=37)};j=job(assets)
    p=Packer(assets,j['settings']).finish();assert len(p)==37
    assert len({x['instance'] for x in p})==37
    assert validate(j,assets,p)['valid']
    assert not validate(j,assets,p[:-1])['valid']

def test_pdf_export_vectors_and_arbitrary_matrix(tmp_path):
    f=tmp_path/'source.pdf';pdf_logo(f)
    folder=tmp_path/'assets';a=ingest(f.read_bytes(),f.name,folder/'a')[0];a.update(id='a',quantity=1,rotation_locked=False)
    assets={'a':a};j=job(assets)
    from backend.vector_io import local_geometry
    for angle in (0,7,43,90,126,218,337):
        g=affinity.rotate(local_geometry(a),angle,origin=(0,0));x,y,_,_=g.bounds
        p={'asset_id':'a','instance':'a:0','x':5-x,'y':5-y,'angle':angle};j['best']=[p]
        f=tmp_path/f'out-{angle}.pdf';r=export_pdf(j,assets,folder,f)
        doc=fitz.open(f);page=doc[0]
        assert len(page.get_images())==0 and len(page.get_drawings())==1
        assert page.rect.width/PT==pytest.approx(580,abs=.001)
        assert page.rect.height/PT==pytest.approx(r['length'],abs=.001)
        drawing=page.get_drawings()[0]
        points=[]
        for item in drawing['items']:
            if item[0]=='l':points.extend([(p.x/PT,p.y/PT) for p in item[1:]])
            if item[0]=='re':points.extend([(p.x/PT,p.y/PT) for p in (item[1].tl,item[1].tr,item[1].br,item[1].bl)])
        poly=Polygon(points).convex_hull
        assert poly.area==pytest.approx(800,abs=.03)
        # Original artwork must lie within independently transformed guard.
        expected=placed_geometry(a,p)
        assert expected.buffer(.002).covers(poly)
        doc.close()

def test_svg_mm_transform_clip_and_fill():
    data=b'<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" viewBox="0 0 100 100"><defs><clipPath id="c"><rect x="0" y="0" width="30" height="25"/></clipPath></defs><g transform="translate(10 20)" clip-path="url(#c)"><path fill="white" d="M0 0H50V40H0Z"/></g></svg>'
    g=SVGGeometry(data).geometry();assert g.area==pytest.approx(750,abs=6);assert g.bounds[0]==pytest.approx(10,abs=.05)

def test_svg_holes_and_open_concavity():
    data=b'<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" viewBox="0 0 100 100"><path fill-rule="evenodd" d="M10 10H90V90H10Z M30 30H70V70H30Z"/></svg>'
    g=SVGGeometry(data).geometry();assert g.contains(Point(50,50))

@pytest.mark.parametrize('bad',[b'<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm"><script>alert(1)</script></svg>',b'<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]><svg width="10mm" height="10mm">&x;</svg>',b'<svg width="10mm" height="10mm"><image href="https://evil.invalid/a.png"/></svg>',b'<svg width="10mm" height="10mm"><use href="#a" id="a"/></svg>'])
def test_svg_security(bad):
    with pytest.raises(Exception):SVGGeometry(bad).geometry()

def test_raster_rejected(tmp_path):
    from PIL import Image
    import io
    b=io.BytesIO();Image.new('RGB',(10,10),'white').save(b,format='PNG')
    d=fitz.open();p=d.new_page();p.insert_image(p.rect,stream=b.getvalue());data=d.tobytes()
    with pytest.raises(ValueError,match='raster'):ingest(data,'image.pdf',tmp_path)

def test_cmyk_svg_is_blocked(tmp_path):
    f=tmp_path/'c.pdf';d=fitz.open();p=d.new_page(width=60*PT,height=40*PT);p.draw_rect(fitz.Rect(5*PT,5*PT,45*PT,25*PT),fill=(0,.4,1,0),color=None);d.save(f)
    a=ingest(f.read_bytes(),'c.pdf',tmp_path/'assets'/'a')[0];a.update(id='a');assets={'a':a};j=job(assets);j['best']=Packer(assets,j['settings']).finish()
    assert a['non_rgb']
    with pytest.raises(ValueError,match='CMYK'):export_svg(j,assets,tmp_path/'assets',tmp_path/'out.svg')
    export_pdf(j,assets,tmp_path/'assets',tmp_path/'out.pdf')
    import pikepdf
    with pikepdf.open(tmp_path/'out.pdf') as result:
        assert any(b' k' in o.read_bytes() for o in result.objects if isinstance(o,pikepdf.Stream))

def test_vector_svg_output(tmp_path):
    data=b'<svg xmlns="http://www.w3.org/2000/svg" width="40mm" height="20mm" viewBox="0 0 40 20"><path fill="white" d="M0 0H40V20H0Z"/></svg>'
    a=ingest(data,'a.svg',tmp_path/'assets'/'a')[0];a.update(id='a',quantity=3);assets={'a':a};j=job(assets);j['best']=Packer(assets,j['settings']).finish()
    export_svg(j,assets,tmp_path/'assets',tmp_path/'out.svg')
    output=(tmp_path/'out.svg').read_text();assert '580mm' in output and '<image' not in output
    assert output.count('href="#logo-a"')==3
