import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Literal
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Response, Depends, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from . import store
from .validation import validate
from .vector_io import MAX_UPLOAD, export_pdf, export_svg

log=logging.getLogger('ast.api')
ACTIVE={'running','pausing','stopping'}
FRONTEND=Path(__file__).resolve().parent.parent/'frontend'/'dist'
SESSION_DAYS=30

def secret():
    value=os.getenv('AST_SECRET','')
    if len(value)<32 or value.startswith('CHANGE_TO_'):raise RuntimeError('AST_SECRET en az 32 rastgele karakter olmalı. README kurulum adımını uygulayın.')
    return value

def accounts():
    # Mapping username -> scrypt salt:hash, generated with manage.py.
    f=store.DATA/'users.json'
    if not f.exists():return {}
    return json.loads(f.read_text())

def token(user):
    payload=f'{user}|{int(time.time())+SESSION_DAYS*86400}'
    return payload+'|'+hmac.new(secret().encode(),payload.encode(),'sha256').hexdigest()

def owner(request:Request):
    cookie=request.cookies.get('ast_session','')
    try:
        user,expiry,sig=cookie.split('|');payload=user+'|'+expiry
        if int(expiry)<time.time() or not hmac.compare_digest(sig,hmac.new(secret().encode(),payload.encode(),'sha256').hexdigest()) or user not in accounts():raise ValueError()
    except Exception:raise HTTPException(401,'Oturum açın.')
    if request.method not in ('GET','HEAD','OPTIONS'):
        # Reject browser cross-origin writes; custom header forces CORS preflight.
        if request.headers.get('x-ast-request')!='1':raise HTTPException(403,'İstek güvenlik doğrulaması başarısız.')
        origin=request.headers.get('origin')
        allowed=os.getenv('AST_ORIGIN')
        if origin and allowed and origin.rstrip('/')!=allowed.rstrip('/'):raise HTTPException(403,'İstek kaynağı uygun değil.')
        if request.headers.get('sec-fetch-site')=='cross-site':raise HTTPException(403,'Siteler arası istek reddedildi.')
    return user

def get_job(jid,user):
    job=store.get(jid,user)
    if not job:raise HTTPException(404,'İş bulunamadı.')
    return job

def public(job):
    return {**{k:v for k,v in job.items() if k not in ('owner','checkpoint')},'partial_count':len((job.get('checkpoint') or {}).get('placements',[])),
            'assets':[{k:v for k,v in a.items() if k not in ('geometry','pdf','svg')} for a in job['assets']]}

def idle(job):
    if job['status'] in ACTIVE or job['status']=='importing':raise HTTPException(409,'Önce optimizasyonu duraklatın veya durdurun.')

def invalidate(j):
    j.update(best=[],best_length=None,initial_length=None,attempts=0,elapsed=0.,last_improvement=None,checkpoint=None,validation=None,status='draft',error=None,revision=j['revision']+1)

@asynccontextmanager
async def lifespan(app):
    secret();store.init()
    # One API process is supported. Recover uploads interrupted by its restart.
    for j in store.all_jobs():
        if j['status']=='importing':store.mutate(j['id'],lambda row:row.update(status='draft',error='Sunucu yeniden başladı; yarım kalan dosyayı yeniden yükleyin.'))
    for base in (store.DATA/'exports',):
        if base.exists():
            for f in base.iterdir():
                if f.is_file() and time.time()-f.stat().st_mtime>86400:f.unlink(missing_ok=True)
    for directory in (store.DATA/'jobs').glob('*/assets/import-*') if (store.DATA/'jobs').exists() else []:
        shutil.rmtree(directory,ignore_errors=True)
    yield

app=FastAPI(title='AST DTF NESTING PRO',version='0.1.0',lifespan=lifespan)

@app.middleware('http')
async def headers(request,call_next):
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['Cache-Control']='no-store'
    response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    return response

class Model(BaseModel):model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
class Login(Model):username:str=Field(min_length=1,max_length=60);password:str=Field(min_length=1,max_length=256)
login_attempts={}
@app.post('/api/login')
def login(data:Login,response:Response,request:Request):
    ip=request.client.host if request.client else 'local';now=time.time();history=[t for t in login_attempts.get(ip,[]) if now-t<60]
    if len(history)>=10:raise HTTPException(429,'Çok fazla giriş denemesi; bir dakika bekleyin.')
    login_attempts[ip]=history+[now]
    record=accounts().get(data.username,'')
    try:
        salt,digest=record.split(':');actual=hashlib.scrypt(data.password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
        if not hmac.compare_digest(actual,digest):raise ValueError()
    except Exception:raise HTTPException(401,'Kullanıcı adı veya parola yanlış.')
    response.set_cookie('ast_session',token(data.username),httponly=True,secure=os.getenv('AST_SECURE_COOKIE','1')=='1',samesite='strict',max_age=SESSION_DAYS*86400)
    return {'username':data.username}

@app.post('/api/logout')
def logout(response:Response,user=Depends(owner)):response.delete_cookie('ast_session');return {'ok':True}
@app.get('/api/me')
def me(user=Depends(owner)):return {'username':user}
@app.get('/api/health')
def health():return {'status':'ok','version':'0.1.0'}
@app.get('/api/jobs')
def list_jobs(user=Depends(owner)):
    return [{k:j.get(k) for k in ('id','name','created','updated','status','best_length')} for j in store.all_jobs(user)]
class NewJob(Model):name:str=Field(min_length=1,max_length=160)
@app.post('/api/jobs')
def new_job(data:NewJob,user=Depends(owner)):return public(store.new(user,data.name))
@app.get('/api/jobs/{jid}')
def read_job(jid:str,user=Depends(owner)):return public(get_job(jid,user))
class Settings(Model):
    width:float=Field(580,ge=20,le=2000);margin:float=Field(5,ge=0,le=100)
    gap:float=Field(3,ge=.1,le=50);mode:Literal['quick','balanced','maximum']='maximum'
    budget_seconds:int=Field(1800,ge=5,le=7200)
@app.put('/api/jobs/{jid}/settings')
def settings(jid:str,data:Settings,user=Depends(owner)):
    if data.width<=2*data.margin:raise HTTPException(422,'Kenar payı film genişliğini aşıyor.')
    def update(j):idle(j);j['settings']=data.model_dump();invalidate(j)
    get_job(jid,user);return public(store.mutate(jid,update,user))

@app.post('/api/jobs/{jid}/assets')
async def upload(jid:str,file:UploadFile=File(...),user=Depends(owner)):
    job=get_job(jid,user);idle(job)
    if len(job['assets'])>=100:raise HTTPException(422,'Bir işte en fazla 100 logo grubu olabilir.')
    data=await file.read(MAX_UPLOAD+1)
    if len(data)>MAX_UPLOAD:raise HTTPException(413,'Dosya en fazla 25 MB olabilir.')
    name=Path(file.filename or 'logo.pdf').name[:180]
    # Prevent concurrent import/run edits by transactionally taking a job lease.
    previous=job['status']
    def importing(j):
        idle(j)
        if j['status']=='importing':raise HTTPException(409,'Dosya işleniyor; bitmesini bekleyin.')
        j['status']='importing'
    store.mutate(jid,importing,user)
    base=store.assets_dir(jid);base.mkdir(parents=True,exist_ok=True)
    tmp=Path(tempfile.mkdtemp(prefix='import-',dir=base));source=tmp/'source';source.write_bytes(data);out=tmp/'result.json'
    try:
        proc=await asyncio.create_subprocess_exec(sys.executable,'-m','backend.import_task',str(source),name,str(tmp),str(out),stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.PIPE,env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})
        try:_,err=await asyncio.wait_for(proc.communicate(),timeout=60)
        except asyncio.TimeoutError:
            proc.kill();await proc.wait();raise HTTPException(422,'Dosya analizi 60 saniyeyi aştı; logoları ayrı dosya yükleyin.')
        if not out.exists():
            log.error('Import crashed: %s',err[-2000:].decode(errors='replace'));raise HTTPException(422,'Dosya güvenli kaynak sınırları içinde işlenemedi.')
        result=json.loads(out.read_text())
        if 'error' in result:raise HTTPException(422,result['error'])
        original_id=str(uuid.uuid4())
        originals=store.DATA/'jobs'/jid/'originals';originals.mkdir(parents=True,exist_ok=True)
        original_path=originals/(original_id+Path(name).suffix.lower());original_path.write_bytes(data)
        added=[]
        for a in result['assets']:
            aid=str(uuid.uuid4());target=base/aid;target.mkdir()
            for key in ('pdf','svg'):shutil.move(str(tmp/a[key]),target/a[key])
            a.update(id=aid,original_file=original_path.name,original_name=name);added.append(a)
        def commit(j):
            if len(j['assets'])+len(added)>100:raise HTTPException(422,'En fazla 100 logo grubu olabilir.')
            j['assets']+=added;invalidate(j)
        return public(store.mutate(jid,commit,user))
    finally:
        shutil.rmtree(tmp,ignore_errors=True)
        def release(j):
            if j['status']=='importing':j['status']=previous
        store.mutate(jid,release,user)

class AssetEdit(Model):
    quantity:int=Field(ge=1,le=1000);width:float=Field(gt=.5,le=3000)
    rotation_locked:bool;confirmed:bool
@app.patch('/api/jobs/{jid}/assets/{aid}')
def edit_asset(jid:str,aid:str,data:AssetEdit,user=Depends(owner)):
    get_job(jid,user)
    def update(j):
        idle(j)
        if j['status']=='importing':raise HTTPException(409,'Dosya işleniyor.')
        a=next((a for a in j['assets'] if a['id']==aid),None)
        if not a:raise HTTPException(404,'Logo bulunamadı.')
        if sum(x['quantity'] for x in j['assets'] if x['id']!=aid)+data.quantity>1000:raise HTTPException(422,'Bir işte en fazla 1000 baskı destekleniyor.')
        a.update(data.model_dump());a['height']=a['native_height']*a['width']/a['native_width'];invalidate(j)
    return public(store.mutate(jid,update,user))
@app.delete('/api/jobs/{jid}/assets/{aid}')
def delete_asset(jid:str,aid:str,user=Depends(owner)):
    get_job(jid,user)
    def update(j):
        idle(j)
        if j['status']=='importing':raise HTTPException(409,'Dosya işleniyor.')
        if not any(a['id']==aid for a in j['assets']):raise HTTPException(404,'Logo bulunamadı.')
        j['assets']=[a for a in j['assets'] if a['id']!=aid];invalidate(j)
    j=store.mutate(jid,update,user);shutil.rmtree(store.assets_dir(jid)/aid,ignore_errors=True);return public(j)
@app.get('/api/jobs/{jid}/assets/{aid}/preview')
def preview(jid:str,aid:str,user=Depends(owner)):
    j=get_job(jid,user);a=next((a for a in j['assets'] if a['id']==aid),None)
    if not a:raise HTTPException(404,'Logo bulunamadı.')
    return FileResponse(store.assets_dir(jid)/aid/a['svg'],media_type='image/svg+xml')

class Action(Model):action:Literal['start','pause','resume','stop','save']
@app.post('/api/jobs/{jid}/action')
def action(jid:str,data:Action,user=Depends(owner)):
    get_job(jid,user)
    def update(j):
        cmd=data.action
        if cmd in ('start','resume'):
            if j['status'] in ACTIVE or j['status']=='importing':raise HTTPException(409,'İş zaten çalışıyor veya dosya işleniyor.')
            if not j['assets'] or not all(a['confirmed'] for a in j['assets']):raise HTTPException(422,'Her sayfanın tek bir bütün logo grubu olduğunu onaylayın.')
            if sum(a['quantity'] for a in j['assets'])>1000:raise HTTPException(422,'Adet sınırı 1000.')
            j['status']='running';j['error']=None
            if j['elapsed']>=j['settings']['budget_seconds']:j['settings']['budget_seconds']=min(86400,j['elapsed']+1800)
        elif cmd=='pause':
            if j['status']!='running':raise HTTPException(409,'Çalışan iş yok.')
            j['status']='pausing'
        elif cmd=='stop':
            if j['status'] in ACTIVE:j['status']='stopping'
            elif j['status']=='importing':raise HTTPException(409,'Dosya işleniyor; bitmesini bekleyin.')
            else:j['status']='stopped';j['checkpoint']=None
        else:
            if not j['best']:raise HTTPException(422,'Henüz kaydedilecek geçerli tam yerleşim yok.')
            report=validate(j,{a['id']:a for a in j['assets']},j['best'])
            if not report['valid']:raise HTTPException(422,'Yerleşim geçersiz.')
            j['snapshot']={'placements':j['best'],'validation':report,'saved_at':time.time()}
    return public(store.mutate(jid,update,user))

class Position(Model):instance:str;x:float;y:float;angle:float=Field(ge=0,lt=360)
@app.patch('/api/jobs/{jid}/placement')
def edit_position(jid:str,data:Position,user=Depends(owner)):
    get_job(jid,user)
    def update(j):
        idle(j)
        p=next((p for p in j['best'] if p['instance']==data.instance),None)
        if not p:raise HTTPException(404,'Baskı bulunamadı.')
        p.update(x=data.x,y=data.y,angle=data.angle)
        report=validate(j,{a['id']:a for a in j['assets']},j['best'])
        if not report['valid']:raise HTTPException(422,'Düzenleme uygulanmadı: '+'; '.join(report['errors'][:3]))
        j['validation']=report;j['best_length']=report['length'];j['checkpoint']=None;j['status']='paused'
    return public(store.mutate(jid,update,user))
@app.get('/api/jobs/{jid}/export/{fmt}')
def export(jid:str,fmt:str,user=Depends(owner)):
    j=get_job(jid,user)
    if not j['best']:raise HTTPException(422,'Henüz geçerli tam yerleşim yok.')
    if fmt not in ('pdf','svg'):raise HTTPException(404,'Çıktı biçimi bulunamadı.')
    assets={a['id']:a for a in j['assets']}
    folder=store.DATA/'exports';folder.mkdir(exist_ok=True)
    path=folder/(str(uuid.uuid4())+'.'+fmt)
    try:
        (export_pdf if fmt=='pdf' else export_svg)(j,assets,store.assets_dir(jid),path)
    except ValueError as exc:path.unlink(missing_ok=True);raise HTTPException(422,str(exc))
    from starlette.background import BackgroundTask
    return FileResponse(path,media_type='application/pdf' if fmt=='pdf' else 'image/svg+xml',filename='AST-'+jid[:8]+'.'+fmt,background=BackgroundTask(path.unlink,missing_ok=True))
@app.get('/api/jobs/{jid}/events')
async def events(jid:str,request:Request,user=Depends(owner)):
    get_job(jid,user)
    async def generate():
        last=None
        while not await request.is_disconnected():
            j=get_job(jid,user)
            if j['updated']!=last:
                last=j['updated'];yield 'data: '+json.dumps(public(j))+'\n\n'
            else:yield ': heartbeat\n\n'
            await asyncio.sleep(1)
    return StreamingResponse(generate(),media_type='text/event-stream',headers={'X-Accel-Buffering':'no'})

if FRONTEND.exists():app.mount('/',StaticFiles(directory=FRONTEND,html=True),name='frontend')
