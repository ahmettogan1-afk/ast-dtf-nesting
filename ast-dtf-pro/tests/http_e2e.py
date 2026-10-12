"""Actual HTTP + separate persistent worker restart; no browser claims."""
import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import httpx

if __name__=='__main__':
    source=Path(sys.argv[1]);report_path=Path(sys.argv[2])
    with tempfile.TemporaryDirectory(prefix='ast-http-') as tmp:
        salt=secrets.token_bytes(16);password=secrets.token_urlsafe(20)
        Path(tmp,'users.json').write_text(json.dumps({'ast':salt.hex()+':'+hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1).hex()}))
        env={**os.environ,'AST_DATA':tmp,'AST_SECRET':secrets.token_urlsafe(48),'AST_SECURE_COOKIE':'0','OPENBLAS_NUM_THREADS':'1'}
        logs=open(Path(tmp,'server.log'),'w')
        server=subprocess.Popen([sys.executable,'-m','uvicorn','backend.api:app','--host','127.0.0.1','--port','8765'],env=env,stdout=logs,stderr=logs)
        worker=None
        try:
            with httpx.Client(base_url='http://127.0.0.1:8765',timeout=90,trust_env=False,headers={'X-AST-Request':'1'}) as c:
                for _ in range(100):
                    try:
                        if c.get('/api/health').status_code==200:break
                    except httpx.ConnectError:pass
                    time.sleep(.1)
                assert c.get('/').status_code==200
                assert c.post('/api/login',json={'username':'ast','password':password}).status_code==200
                j=c.post('/api/jobs',json={'name':'BRZ gerçek HTTP testi'}).json();jid=j['id'];base='/api/jobs/'+jid
                r=c.post(base+'/assets',files={'file':(source.name,source.read_bytes(),'application/pdf')});assert r.status_code==200,r.text
                a=r.json()['assets'][0]
                r=c.patch(base+'/assets/'+a['id'],json={'quantity':37,'width':a['width'],'confirmed':True,'rotation_locked':False});assert r.status_code==200,r.text
                c.put(base+'/settings',json={'width':580,'margin':5,'gap':3,'mode':'quick','budget_seconds':60})
                worker=subprocess.Popen([sys.executable,'-m','backend.worker'],env=env,stdout=logs,stderr=logs)
                assert c.post(base+'/action',json={'action':'start'}).status_code==200
                for _ in range(200):
                    j=c.get(base).json()
                    if j['partial_count']>=1 or j['best']:break
                    time.sleep(.1)
                assert j['partial_count']>=1, 'Expected durable partial checkpoint before first completion'
                partial=j['partial_count']
                assert c.post(base+'/action',json={'action':'pause'}).status_code==200
                for _ in range(100):
                    j=c.get(base).json()
                    if j['status']=='paused':break
                    time.sleep(.1)
                assert j['status']=='paused',j
                retained=j['partial_count'];worker.terminate();worker.wait(timeout=5)
                worker=subprocess.Popen([sys.executable,'-m','backend.worker'],env=env,stdout=logs,stderr=logs)
                assert c.post(base+'/action',json={'action':'resume'}).status_code==200
                for _ in range(300):
                    j=c.get(base).json()
                    if j['status'] in ('completed','error'):break
                    time.sleep(.1)
                assert j['status']=='completed',j
                output=c.get(base+'/export/pdf');assert output.status_code==200 and output.content.startswith(b'%PDF')
                import pymupdf as fitz
                doc=fitz.open(stream=output.content,filetype='pdf');vectors=len(doc[0].get_drawings());images=len(doc[0].get_images())
                report={'flow':'real HTTP API + separate worker, pause, process restart, resume, download','source':source.name,'count':len(j['best']),'valid':j['validation']['valid'],'length_mm':j['best_length'],'minimum_distance_mm':j['validation']['minimum_distance_mm'],'checkpoint_before_pause':partial,'checkpoint_after_pause':retained,'output_vector_drawings':vectors,'output_images':images,'frontend_http_status':c.get('/').status_code,'browser_test':False,'ipad_safari_test':False}
                assert report['count']==37 and vectors==37*44 and images==0
                report_path.write_text(json.dumps(report,indent=2,ensure_ascii=False));print(json.dumps(report,indent=2,ensure_ascii=False))
        except Exception:
            logs.flush();print(Path(tmp,'server.log').read_text()[-4000:]);raise
        finally:
            if worker:worker.terminate();worker.wait(timeout=5)
            server.terminate();server.wait(timeout=5);logs.close()
