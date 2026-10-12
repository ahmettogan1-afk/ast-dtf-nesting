"""Original PDF is kept separate from derived geometry / screen SVG."""
import io
import json
import re
from pathlib import Path
import xml.etree.ElementTree as XET
import pymupdf as fitz
import pikepdf
from shapely import affinity, wkt
from shapely.geometry import box
from .geometry import SVGGeometry, GUARD, reserve_holes

PT=72/25.4
MAX_UPLOAD=25*1024*1024

def normalize_visible_layers(data):
    """Freeze ONLY unambiguously all-visible OCGs; refuse other configurations."""
    p=pikepdf.open(io.BytesIO(data))
    oc=p.Root.get('/OCProperties')
    if not oc:
        p.close();return data
    default=oc.get('/D',{})
    if str(default.get('/BaseState','/ON'))!='/ON' or default.get('/OFF') or default.get('/AS') or oc.get('/Configs'):
        raise ValueError('Gizli veya koşullu PDF katmanları desteklenmiyor. Baskı görünümünü düzleştirin.')
    for group in oc.get('/OCGs',[]):
        usage=group.get('/Usage',{})
        if any(k in usage for k in ('/View','/Print','/Export','/Zoom','/User','/Language')):
            raise ValueError('Görünüm/baskı koşulu olan PDF katmanı desteklenmiyor.')
    streams=[]
    for page in p.pages:
        instructions=pikepdf.parse_content_stream(page)
        page.Contents=p.make_stream(pikepdf.unparse_content_stream([i for i in instructions if str(i.operator) not in ('BMC','BDC','EMC')]))
    for obj in pdf_objects(p):
        if isinstance(obj,(pikepdf.Dictionary,pikepdf.Stream)):
            if str(obj.get('/Type',''))=='/OCMD':raise ValueError('Koşullu PDF katman üyeliği desteklenmiyor.')
            if '/OC' in obj:del obj['/OC']
            if isinstance(obj,pikepdf.Stream) and str(obj.get('/Subtype',''))=='/Form':streams.append(obj)
    for stream in streams:
        instructions=pikepdf.parse_content_stream(stream)
        stream.write(pikepdf.unparse_content_stream([i for i in instructions if str(i.operator) not in ('BMC','BDC','EMC')]))
    del p.Root['/OCProperties']
    target=io.BytesIO();p.save(target);p.close();return target.getvalue()

def pdf_objects(pdf):
    """Include DIRECT nested dictionaries: Resources/ExtGState often are direct."""
    seen=set()
    def walk(obj,depth=0):
        if depth>80:raise ValueError('PDF nesne ağacı fazla derin.')
        if isinstance(obj,(pikepdf.Dictionary,pikepdf.Stream,pikepdf.Array)):
            if obj.is_indirect:
                if obj.objgen in seen:return
                seen.add(obj.objgen)
            yield obj
            values=obj if isinstance(obj,pikepdf.Array) else obj.values()
            for value in values:yield from walk(value,depth+1)
        else:yield obj
    for obj in pdf.objects:yield from walk(obj)

def pdf_preflight(data):
    warnings=[]; non_rgb=False
    try:
        pdf=pikepdf.open(io.BytesIO(data))
    except Exception as exc:raise ValueError('PDF açılamadı veya şifreli.') from exc
    if pdf.is_encrypted:raise ValueError('Şifreli PDF kabul edilmez.')
    if len(pdf.pages)>30:raise ValueError('En fazla 30 sayfa yükleyin; her sayfa bir logo grubu olacaktır.')
    if any(k in pdf.Root for k in ('/AcroForm','/OCProperties','/OpenAction','/AA','/Perms')):
        raise ValueError('Form, katman, eylem veya imzalı PDF desteklenmiyor. Illustrator’dan düz PDF kaydedin.')
    total=0
    for obj in pdf_objects(pdf):
        if isinstance(obj,pikepdf.Name) and str(obj) in ('/DeviceCMYK','/Separation','/DeviceN','/ICCBased'):non_rgb=True
        if isinstance(obj,(pikepdf.Dictionary,pikepdf.Stream)):
            keys=set(str(k) for k in obj.keys())
            if keys & {'/JavaScript','/JS','/AA','/EF','/EmbeddedFiles'}:
                raise ValueError('PDF etkin içerik veya ekli dosya içeriyor; kabul edilmedi.')
            if str(obj.get('/S','')) in ('/Launch','/JavaScript','/URI','/GoToR'):
                raise ValueError('PDF dış bağlantı/eylem içeriyor; temiz baskı PDF’si yükleyin.')
            if '/Pattern' in keys or '/Shading' in keys:
                if obj.get('/Pattern') or obj.get('/Shading'):raise ValueError('PDF pattern/gradient shading desteklenmiyor.')
            if '/SMask' in keys and str(obj['/SMask'])!='/None':raise ValueError('PDF soft mask desteklenmiyor.')
            if '/BM' in keys and str(obj['/BM']) not in ('/Normal','/Compatible'):raise ValueError('PDF özel karışım modu desteklenmiyor.')
            if str(obj.get('/Subtype','')) in ('/Image','/Type3'):
                raise ValueError('PDF raster görüntü veya Type3 font içeriyor. Bu sürüm yalnızca vektör baskı kabul eder.')
            if str(obj.get('/S',''))=='/Transparency' and bool(obj.get('/K',False)):
                raise ValueError('Knockout saydamlık grubu desteklenmiyor.')
            if any(v in str(obj.get('/ColorSpace','')) for v in ('DeviceCMYK','Separation','DeviceN','ICCBased')):non_rgb=True
            if isinstance(obj,pikepdf.Stream):
                decoded=obj.read_bytes();total+=len(decoded)
                if total>120*1024*1024:raise ValueError('PDF açılmış içerik sınırını aşıyor.')
                if re.search(rb'(?:^|\s)(?:k|K)(?:\s|$)',decoded):non_rgb=True
    if pdf.Root.get('/OutputIntents'):
        warnings.append('Kaynak OutputIntent belgesi çıktı PDF’ye aktarılmıyor; RIP renk profili ayrıca doğrulanmalı.')
        raise ValueError('OutputIntent/ICC üretim profilli PDF bu sürümde desteklenmiyor; profil koruması doğrulanmadan kabul edilmiyor.')
    pdf.close()
    return non_rgb,warnings

def ingest(data,filename,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    if len(data)>MAX_UPLOAD:raise ValueError('Dosya en fazla 25 MB olabilir.')
    ext=Path(filename).suffix.lower()
    is_svg=ext=='.svg'
    if ext in ('.eps',):raise ValueError('EPS desteklenmiyor. Illustrator’dan PDF uyumlu, tek logo/sayfa PDF kaydedin.')
    if ext not in ('.svg','.pdf','.ai'):raise ValueError('PDF, SVG veya PDF uyumlu AI yükleyin.')
    if is_svg:
        # Validate source before handing it to any renderer. No external fetches.
        check=SVGGeometry(data);check.geometry()
        source=fitz.open(stream=data,filetype='svg')
        data=source.convert_to_pdf();source.close()
    elif not data.lstrip().startswith(b'%PDF-'):
        raise ValueError('AI dosyası PDF uyumlu kaydedilmemiş. Illustrator’da PDF Uyumluluğu seçeneğini açın.')
    data=normalize_visible_layers(data)
    non_rgb,warnings=pdf_preflight(data)
    doc=fitz.open(stream=data,filetype='pdf')
    results=[]
    if not len(doc):raise ValueError('PDF boş.')
    for idx,page in enumerate(doc):
        if page.rotation:raise ValueError('PDF sayfa rotasyonu desteklenmiyor; Illustrator’da çalışma yüzeyini düz kaydedin.')
        if page.first_annot or page.first_widget or page.get_links():raise ValueError('PDF açıklama, form veya bağlantı içeriyor; temiz baskı PDF’si yükleyin.')
        for font in page.get_fonts(full=True):
            xref,extn,kind,name=font[:4]
            if extn=='n/a' or kind=='Type3':raise ValueError(f'Font gömülü değil veya desteklenmiyor: {name}. Metni kontura çevirin.')
        if page.get_image_info():raise ValueError('PDF raster görüntü içeriyor; vektör olarak işlenmedi.')
        if page.rect.width>10000*PT or page.rect.height>10000*PT:raise ValueError('Sayfa ölçüsü sınırı aşıldı.')
        svg=page.get_svg_image(text_as_path=True)
        engine=SVGGeometry(svg.encode(),pdf_points=True)
        g=engine.geometry()
        # Crop only the page viewport, never delete any painted white object.
        b=g.bounds;clip=fitz.Rect(max(0,b[0]*PT),max(0,b[1]*PT),min(page.rect.width,b[2]*PT),min(page.rect.height,b[3]*PT))
        out=fitz.open();p=out.new_page(width=clip.width,height=clip.height)
        p.show_pdf_page(p.rect,doc,idx,clip=clip)
        name=f'page-{idx+1}'
        pdf_path=folder/(name+'.pdf');out.save(pdf_path,deflate=True)
        preview=p.get_svg_image(text_as_path=True)
        # Analyze the exact normalized form that will be printed.
        normalized=SVGGeometry(preview.encode(),pdf_points=True);raw=normalized.geometry(guarded=False)
        nx,ny,nxx,nyy=raw.bounds
        geom=affinity.translate(reserve_holes(raw.buffer(GUARD,quad_segs=16,join_style=2)),-nx,-ny)
        (folder/(name+'.svg')).write_text(preview)
        ww,hh=nxx-nx,nyy-ny
        info={'name':filename+(f' · Sayfa {idx+1}' if len(doc)>1 else ''),'pdf':pdf_path.name,'svg':name+'.svg',
              'geometry':geom.wkt,'canvas_width':p.rect.width/PT,'canvas_height':p.rect.height/PT,'offset_x':-nx,'offset_y':-ny,'native_width':ww,'native_height':hh,'width':ww,'height':hh,
              'quantity':1,'rotation_locked':False,'confirmed':False,'non_rgb':non_rgb,
              'white_background':engine.white_background,'warnings':warnings+[
                  'Sayfa bir bütün logo grubu olarak tutuldu. Birden fazla bağımsız logo varsa ayrı sayfa/dosya yükleyin.',
                  'Ekran önizlemesi RGB’dir; baskı PDF’si kaynak vektör nesnelerini kullanır.'
              ],'vector_paths':len(p.get_drawings()),'fonts':len(page.get_fonts()),'guard_mm':GUARD}
        if engine.white_background:info['warnings'].append('Sayfayı kaplayan beyaz nesne var. Silinmedi; baskıya DAHİL. İstenmiyorsa kaynak dosyada kaldırıp yeniden yükleyin.')
        results.append(info);out.close()
    doc.close()
    return results

def local_geometry(asset):
    return affinity.scale(wkt.loads(asset['geometry']),xfact=asset['width']/asset['native_width'],yfact=asset['width']/asset['native_width'],origin=(0,0))

def placed_geometry(asset,placement):
    return affinity.translate(affinity.rotate(local_geometry(asset),placement['angle'],origin=(0,0)),placement['x'],placement['y'])

def export_pdf(job,assets,directory,output):
    from .validation import validate
    report=validate(job,assets,job['best'])
    if not report['valid']:raise ValueError('Geometri doğrulanamadı: '+'; '.join(report['errors'][:5]))
    length=report['length'];width=job['settings']['width']
    if max(length,width)*PT>14400:raise ValueError('Tek PDF sayfası 5080 mm sınırını aşıyor. İşi daha küçük partilere bölün; sessiz ölçekleme yapılmadı.')
    doc=fitz.open();page=doc.new_page(width=width*PT,height=length*PT)
    opened={}
    try:
        for placement in job['best']:
            a=assets[placement['asset_id']]
            if a['id'] not in opened:opened[a['id']]=fitz.open(Path(directory)/a['id']/a['pdf'])
            src=opened[a['id']]
            scale=a['width']/a['native_width']
            rect=affinity.translate(affinity.rotate(box(a.get('offset_x',0)*scale,a.get('offset_y',0)*scale,(a.get('offset_x',0)+a.get('canvas_width',a['native_width']))*scale,(a.get('offset_y',0)+a.get('canvas_height',a['native_height']))*scale),placement['angle'],origin=(0,0)),placement['x'],placement['y'])
            dest=fitz.Rect(*(v*PT for v in rect.bounds))
            page.show_pdf_page(dest,src,0,rotate=-placement['angle'],keep_proportion=True)
        doc.set_metadata({'title':job['name'],'producer':'AST DTF NESTING PRO · original vector Form XObjects'})
        doc.save(output,deflate=True,garbage=4)
    finally:
        doc.close()
        for d in opened.values():d.close()
    return report

def export_svg(job,assets,directory,output):
    from .validation import validate
    report=validate(job,assets,job['best'])
    if not report['valid']:raise ValueError('Yerleşim doğrulanamadı.')
    if any(assets[p['asset_id']]['non_rgb'] for p in job['best']):
        raise ValueError('CMYK/spot/ICC renkler SVG’ye kayıpsız taşınamıyor. Orijinal renkleri korumak için PDF indirin.')
    ns='http://www.w3.org/2000/svg'
    XET.register_namespace('',ns)
    root=XET.Element('{'+ns+'}svg',{'width':f"{job['settings']['width']}mm",'height':f"{report['length']}mm",'viewBox':f"0 0 {job['settings']['width']} {report['length']}"})
    defs=XET.SubElement(root,'{'+ns+'}defs')
    for aid in {p['asset_id'] for p in job['best']}:
        a=assets[aid];element=XET.fromstring((Path(directory)/aid/a['svg']).read_text())
        prefix='a'+aid.replace('-','')+'_'
        for e in element.iter():
            if 'id' in e.attrib:e.set('id',prefix+e.get('id'))
            for key,value in list(e.attrib.items()):
                value=re.sub(r'url\(#([^)]*)\)',lambda m:'url(#'+prefix+m[1]+')',value)
                if key.endswith('href') and value.startswith('#'):value='#'+prefix+value[1:]
                e.set(key,value)
        symbol=XET.SubElement(defs,'{'+ns+'}g',{'id':'logo-'+aid})
        for child in element:symbol.append(child)
    for p in job['best']:
        a=assets[p['asset_id']];s=a['width']/a['native_width']/PT
        XET.SubElement(root,'{'+ns+'}use',{'href':'#logo-'+a['id'],'transform':f"translate({p['x']} {p['y']}) rotate({p['angle']}) scale({s}) translate({a.get('offset_x',0)*PT} {a.get('offset_y',0)*PT})"})
    XET.ElementTree(root).write(output,encoding='utf-8',xml_declaration=True)
    return report
