import hashlib
import importlib
import json
import time
import pytest
from fastapi.testclient import TestClient
from backend import store
from backend.api import app
from backend.worker import run_attempt

SVG=b'<svg xmlns="http://www.w3.org/2000/svg" width="20mm" height="10mm" viewBox="0 0 20 10"><path fill="white" d="M0 0H20V10H0Z"/></svg>'

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path);monkeypatch.setattr(store,'DB',tmp_path/'ast.sqlite')
    monkeypatch.setenv('AST_SECRET','test-only-secret-not-for-deployment-123456789')
    monkeypatch.setenv('AST_SECURE_COOKIE','0');monkeypatch.setenv('AST_DATA',str(tmp_path))
    salt=bytes.fromhex('11'*16)
    digest=hashlib.scrypt(b'test-password-long',salt=salt,n=16384,r=8,p=1).hex()
    (tmp_path/'users.json').write_text(json.dumps({'ast':salt.hex()+':'+digest,'other':salt.hex()+':'+digest}))
    with TestClient(app) as c:
        r=c.post('/api/login',json={'username':'ast','password':'test-password-long'});assert r.status_code==200
        c.headers['X-AST-Request']='1';yield c

def test_http_full_flow_and_persistence(client):
    c=client
    j=c.post('/api/jobs',json={'name':'API test'}).json();jid=j['id']
    r=c.post(f'/api/jobs/{jid}/assets',files={'file':('logo.svg',SVG,'image/svg+xml')});assert r.status_code==200,r.text
    a=r.json()['assets'][0]
    r=c.patch(f'/api/jobs/{jid}/assets/{a["id"]}',json={'quantity':37,'width':20,'confirmed':True,'rotation_locked':False});assert r.status_code==200,r.text
    assert r.json()['assets'][0]['height']/r.json()['assets'][0]['width']==pytest.approx(a['height']/a['width'])
    c.put(f'/api/jobs/{jid}/settings',json={'width':580,'margin':5,'gap':3,'mode':'quick','budget_seconds':60})
    r=c.post(f'/api/jobs/{jid}/action',json={'action':'start'});assert r.status_code==200,r.text
    run_attempt(jid)
    result=c.get(f'/api/jobs/{jid}').json()
    assert result['status']=='completed',result
    assert len(result['best'])==37
    assert result['validation']['valid']
    assert store.get(jid,'ast')['best']==result['best']
    assert c.get(f'/api/jobs/{jid}/export/pdf').content.startswith(b'%PDF')
    svg=c.get(f'/api/jobs/{jid}/export/svg');assert svg.status_code==200
    assert c.post(f'/api/jobs/{jid}/action',json={'action':'save'}).status_code==200
    assert store.get(jid)['snapshot']['validation']['valid']
    p=result['best'][0]
    r=c.patch(f'/api/jobs/{jid}/placement',json={'instance':p['instance'],'x':-100,'y':0,'angle':0})
    assert r.status_code==422
    assert c.get(f'/api/jobs/{jid}').json()['best'][0]==p

def test_isolation_and_csrf(client):
    c=client;jid=c.post('/api/jobs',json={'name':'private'}).json()['id']
    c.headers.pop('X-AST-Request')
    assert c.post('/api/jobs',json={'name':'csrf'}).status_code==403
    c.headers['X-AST-Request']='1'
    c.post('/api/login',json={'username':'other','password':'test-password-long'})
    assert c.get('/api/jobs/'+jid).status_code==404
    assert c.get('/api/jobs').json()==[]

def test_upload_failures_not_success(client):
    c=client;jid=c.post('/api/jobs',json={'name':'bad'}).json()['id']
    r=c.post(f'/api/jobs/{jid}/assets',files={'file':('bad.svg',b'<svg><script/></svg>','image/svg+xml')})
    assert r.status_code==422
    assert c.get('/api/jobs/'+jid).json()['assets']==[]
    assert c.get('/api/jobs/'+jid).json()['status']=='draft'
    assert c.post(f'/api/jobs/{jid}/action',json={'action':'start'}).status_code==422

def test_pause_resume_checkpoint(client):
    c=client;jid=c.post('/api/jobs',json={'name':'pause'}).json()['id']
    a=c.post(f'/api/jobs/{jid}/assets',files={'file':('logo.svg',SVG)}).json()['assets'][0]
    c.patch(f'/api/jobs/{jid}/assets/{a["id"]}',json={'quantity':12,'width':20,'confirmed':True,'rotation_locked':True})
    c.post(f'/api/jobs/{jid}/action',json={'action':'start'})
    from backend.nesting import Packer
    j=store.get(jid);packer=Packer({a['id']:j['assets'][0]},j['settings'],int(jid.replace('-','')[:8],16),0)
    for _ in range(4):packer.next()
    store.mutate(jid,lambda j:j.update(checkpoint={'attempt':0,'placements':packer.placed}))
    r=c.post(f'/api/jobs/{jid}/action',json={'action':'pause'});assert r.json()['status']=='pausing'
    run_attempt(jid);assert store.get(jid)['status']=='paused'
    assert len(store.get(jid)['checkpoint']['placements'])==4
    c.post(f'/api/jobs/{jid}/action',json={'action':'resume'})
    run_attempt(jid)
    result=store.get(jid);assert len(result['best'])==12
    assert result['best'][:4]==packer.placed
    c.post(f'/api/jobs/{jid}/action',json={'action':'stop'})
    run_attempt(jid);assert store.get(jid)['status']=='stopped'
