"""Pass a real isolated logo PDF; source user files are not committed."""
import argparse
import json
import time
from pathlib import Path
import pymupdf as fitz
from backend.vector_io import ingest,export_pdf,PT
from backend.nesting import Packer
from backend.validation import validate

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('source');ap.add_argument('--output',default='examples/real-brz');args=ap.parse_args()
    root=Path(args.output);root.mkdir(parents=True,exist_ok=True);f=Path(args.source)
    start=time.perf_counter();a=ingest(f.read_bytes(),f.name,root/'assets'/'brz')[0];analysis=time.perf_counter()-start
    a.update(id='brz',quantity=37,confirmed=True,rotation_locked=False)
    assets={'brz':a};j={'id':'brz-reference','name':'BRZ · 37 adet gerçek dosya testi','settings':{'width':580,'margin':5,'gap':3,'mode':'quick'}}
    start=time.perf_counter();j['best']=Packer(assets,j['settings']).finish();packing=time.perf_counter()-start
    r=validate(j,assets,j['best']);pdf=root/'BRZ_37_ADet_580mm.pdf';export_pdf(j,assets,root/'assets',pdf)
    with fitz.open(pdf) as d:
        checks={'output_vector_drawings':len(d[0].get_drawings()),'expected_vector_drawings':a['vector_paths']*37,'output_images':len(d[0].get_images()),'page_width_mm':d[0].rect.width/PT,'page_height_mm':d[0].rect.height/PT}
    report={'source':f.name,'analysis_seconds':analysis,'packing_seconds':packing,'copies':37,'logo_width_mm':a['width'],'logo_height_mm':a['height'],'native_scale':1,'color_non_rgb':a['non_rgb'],'validation':r,**checks}
    assert r['valid'] and checks['output_images']==0 and checks['output_vector_drawings']==checks['expected_vector_drawings']
    (root/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False));(root/'placements.json').write_text(json.dumps(j,indent=2,ensure_ascii=False))
    print(json.dumps(report,indent=2,ensure_ascii=False))
