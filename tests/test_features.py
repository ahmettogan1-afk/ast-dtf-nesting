from pathlib import Path
import pymupdf as fitz
import pikepdf
import pytest
from shapely.geometry import Point
from shapely import wkt
from backend.vector_io import ingest,PT
from backend.geometry import SVGGeometry


def test_embedded_text_is_vector_geometry(tmp_path):
    font=Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    if not font.exists():pytest.skip('Fixture font is not installed')
    doc=fitz.open();page=doc.new_page(width=100*PT,height=40*PT)
    page.insert_font(fontname='embedded',fontfile=font)
    page.insert_text((10*PT,25*PT),'AST 37',fontname='embedded',fontsize=30,color=(1,1,1))
    result=ingest(doc.tobytes(),'text.pdf',tmp_path/'out')[0]
    assert result['fonts']>0 and wkt.loads(result['geometry']).area>5
    with fitz.open(tmp_path/'out'/result['pdf']) as check:
        assert 'AST 37' in check[0].get_text() and not check[0].get_images()
        assert check[0].get_fonts()[0][1]!='n/a'


def test_ungembedded_font_refused(tmp_path):
    doc=fitz.open();p=doc.new_page();p.insert_text((50,50),'not embedded')
    with pytest.raises(ValueError,match='Font'):ingest(doc.tobytes(),'font.pdf',tmp_path)


def test_stroke_transparency_preserved(tmp_path):
    doc=fitz.open();p=doc.new_page(width=50*PT,height=40*PT)
    p.draw_line((5*PT,10*PT),(45*PT,30*PT),color=(1,1,1),width=2*PT,stroke_opacity=.5)
    a=ingest(doc.tobytes(),'stroke.pdf',tmp_path/'out')[0]
    assert wkt.loads(a['geometry']).area>85
    with fitz.open(tmp_path/'out'/a['pdf']) as d:assert d[0].get_drawings()[0]['stroke_opacity']==pytest.approx(.5)


def test_white_background_not_deleted(tmp_path):
    doc=fitz.open();p=doc.new_page(width=40*PT,height=20*PT)
    p.draw_rect(p.rect,fill=(1,1,1),color=None)
    p.draw_circle((20*PT,10*PT),5*PT,fill=(1,0,0),color=None)
    a=ingest(doc.tobytes(),'background.pdf',tmp_path/'out')[0]
    assert a['white_background'] and not a['confirmed']
    with fitz.open(tmp_path/'out'/a['pdf']) as d:assert len(d[0].get_drawings())==2


def test_pdf_clipping(tmp_path):
    p=pikepdf.Pdf.new();page=p.add_blank_page(page_size=(100,100));page.Contents=p.make_stream(b'q 10 10 20 30 re W n 1 1 1 rg 0 0 100 100 re f Q')
    f=tmp_path/'clip.pdf';p.save(f)
    a=ingest(f.read_bytes(),'clip.pdf',tmp_path/'out')[0]
    assert a['native_width']==pytest.approx(20/PT,abs=.1)
    assert a['native_height']==pytest.approx(30/PT,abs=.1)


def test_arcs_and_bezier_bounds():
    data=b'<svg width="60mm" height="60mm" viewBox="0 0 60 60"><path d="M10 30 A20 20 0 1 0 50 30 A20 20 0 1 0 10 30Z" fill="white"/></svg>'
    g=SVGGeometry(data).geometry();assert g.contains(Point(30,30));assert g.area>1256
    assert g.bounds[0]<10 and g.bounds[2]>50


def test_spot_white_name_preserved_in_pdf(tmp_path):
    from backend.vector_io import export_pdf
    from backend.nesting import Packer
    source=pikepdf.Pdf.new();page=source.add_blank_page(page_size=(100,60))
    tint=pikepdf.Dictionary(FunctionType=2,Domain=[0,1],C0=[0,0,0,0],C1=[0,0,0,0],N=1)
    page.Resources=pikepdf.Dictionary(ColorSpace=pikepdf.Dictionary(CSW=pikepdf.Array([pikepdf.Name('/Separation'),pikepdf.Name('/DTFWhite'),pikepdf.Name('/DeviceCMYK'),tint])))
    page.Contents=source.make_stream(b'q /CSW cs 1 scn 10 10 60 30 re f Q')
    f=tmp_path/'spot.pdf';source.save(f)
    a=ingest(f.read_bytes(),'spot.pdf',tmp_path/'assets'/'a')[0];a.update(id='a',quantity=2,rotation_locked=False)
    assert a['non_rgb']
    assets={'a':a};job={'name':'Spot test','settings':{'width':580,'margin':5,'gap':3}}
    job['best']=Packer(assets,job['settings']).finish()
    export_pdf(job,assets,tmp_path/'assets',tmp_path/'out.pdf')
    with pikepdf.open(tmp_path/'out.pdf') as output:
        from backend.vector_io import pdf_objects
        spaces=[o for o in pdf_objects(output) if isinstance(o,pikepdf.Array) and len(o)>=2 and str(o[0])=='/Separation']
        assert any(str(o[1])=='/DTFWhite' for o in spaces)
        assert any(b'/CSW cs 1 scn' in o.read_bytes() for o in output.objects if isinstance(o,pikepdf.Stream))


def test_direct_nested_unsupported_blend_rejected(tmp_path):
    p=pikepdf.Pdf.new();page=p.add_blank_page(page_size=(100,100))
    page.Resources=pikepdf.Dictionary(ExtGState=pikepdf.Dictionary(GS=pikepdf.Dictionary(BM=pikepdf.Name('/Multiply'))))
    page.Contents=p.make_stream(b'q /GS gs 1 0 0 rg 10 10 20 20 re f Q')
    f=tmp_path/'blend.pdf';p.save(f)
    with pytest.raises(ValueError,match='karışım'):ingest(f.read_bytes(),'blend.pdf',tmp_path/'out')
