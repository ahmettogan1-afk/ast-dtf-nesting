import json
import os
import sqlite3
import time
import uuid
from pathlib import Path

DATA=Path(os.getenv('AST_DATA','./data')).resolve()
DB=DATA/'ast.sqlite'

def connect():
    DATA.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(DB,timeout=30,isolation_level=None)
    con.execute('PRAGMA journal_mode=WAL');con.execute('PRAGMA busy_timeout=30000')
    return con

def init():
    with connect() as c:
        c.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, owner TEXT NOT NULL, updated REAL NOT NULL, payload TEXT NOT NULL)')
        c.execute('CREATE INDEX IF NOT EXISTS jobs_owner ON jobs(owner)')

def save(job):
    job['updated']=time.time()
    with connect() as c:c.execute('INSERT INTO jobs VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET updated=excluded.updated,payload=excluded.payload',(job['id'],job['owner'],job['updated'],json.dumps(job,allow_nan=False)))

def get(jid,owner=None):
    with connect() as c:
        row=c.execute('SELECT payload FROM jobs WHERE id=?'+(' AND owner=?' if owner else ''),(jid,owner) if owner else (jid,)).fetchone()
    return json.loads(row[0]) if row else None

def mutate(jid,fn,owner=None):
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT payload FROM jobs WHERE id=?'+(' AND owner=?' if owner else ''),(jid,owner) if owner else (jid,)).fetchone()
        if not row:c.rollback();raise KeyError(jid)
        j=json.loads(row[0]);fn(j);j['updated']=time.time()
        c.execute('UPDATE jobs SET payload=?,updated=? WHERE id=?',(json.dumps(j,allow_nan=False),j['updated'],jid));c.commit();return j

def all_jobs(owner=None):
    with connect() as c:rows=c.execute('SELECT payload FROM jobs'+(' WHERE owner=?' if owner else '')+' ORDER BY updated DESC',(owner,) if owner else ()).fetchall()
    return [json.loads(r[0]) for r in rows]

def new(owner,name):
    j={'id':str(uuid.uuid4()),'owner':owner,'name':name,'created':time.time(),'updated':time.time(),'settings':{'width':580.,'margin':5.,'gap':3.,'mode':'maximum','budget_seconds':1800},'assets':[], 'status':'draft','best':[],'initial_length':None,'best_length':None,'attempts':0,'elapsed':0.,'last_improvement':None,'checkpoint':None,'validation':None,'revision':0,'error':None}
    save(j);return j

def assets_dir(jid):return DATA/'jobs'/jid/'assets'
