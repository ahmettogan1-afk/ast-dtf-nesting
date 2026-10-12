"""Reproducible benchmark; writes measured values, never predetermined scores."""
import argparse
import json
import time
from pathlib import Path
import resource
from shapely.geometry import Polygon,box
from backend.nesting import Packer
from backend.validation import validate
from tests.test_core import synthetic,job

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='docs/benchmark-results.json');args=parser.parse_args()
    rows=[]
    for n in (500,1000):
        shapes=[Polygon([(0,0),(18,0),(18,7),(7,7),(7,15),(0,15)]),box(0,0,16,12),Polygon([(0,0),(20,0),(10,16)])]
        counts=[n//3,n//3,n-2*(n//3)]
        assets={str(i):synthetic(g,str(i),counts[i]) for i,g in enumerate(shapes)}
        j=job(assets);start=time.perf_counter();p=Packer(assets,j['settings']).finish();packtime=time.perf_counter()-start
        start=time.perf_counter();report=validate(j,assets,p);validationtime=time.perf_counter()-start
        row={'copies':n,'unique_shapes':3,'rotations_locked':True,'packing_seconds':packtime,'validation_seconds':validationtime,'peak_process_rss_mb':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'valid':report['valid'],'length_mm':report['length'],'requested_gap_mm':3,'count':report['count']}
        rows.append(row);print(json.dumps(row),flush=True)
    Path(args.output).write_text(json.dumps(rows,indent=2))
