"""One durable scheduler process. Never run CPU optimization in HTTP requests."""
import logging
import os
import time
import fcntl
from . import store
from .nesting import Packer
from .validation import validate

log=logging.getLogger('ast.worker')

def run_attempt(jid):
    job=store.get(jid);assets={a['id']:a for a in job['assets']}
    checkpoint=job.get('checkpoint') or {};attempt=job['attempts'];seed=attempt+int(jid.replace('-','')[:8],16)
    packer=Packer(assets,job['settings'],seed,attempt)
    if checkpoint.get('attempt')==attempt:
        for p in checkpoint.get('placements',[]):packer.add(p)
    start=time.monotonic();saved=start;last_check=0;halt=False
    def interrupted():
        nonlocal last_check,halt
        now=time.monotonic()
        if now-last_check>.2:
            latest=store.get(jid);last_check=now
            halt=latest['status']!='running'
        return halt
    def checkpoint_save():
        nonlocal saved
        now=time.monotonic();delta=now-saved
        def update(j):
            j['elapsed']+=delta;j['checkpoint']={'attempt':attempt,'placements':packer.placed}
            j['heartbeat']=time.time()
        store.mutate(jid,update);saved=now
    try:
        while len(packer.placed)<len(packer.order):
            p=packer.next(interrupted)
            if p is None:
                checkpoint_save()
                def settled(j):
                    if j['status']=='pausing':j['status']='paused'
                    if j['status']=='stopping':j['status']='stopped';j['checkpoint']=None
                store.mutate(jid,settled);return
            if time.monotonic()-saved>1:checkpoint_save()
        report=validate(job,assets,packer.placed)
        if not report['valid']:raise ValueError('Bağımsız geometri doğrulaması başarısız: '+'; '.join(report['errors'][:3]))
        def commit(j):
            j['elapsed']+=time.monotonic()-saved;j['attempts']+=1;j['checkpoint']=None;j['heartbeat']=time.time()
            if j['best_length'] is None or report['length']<j['best_length']-1e-6:
                if j['initial_length'] is None:j['initial_length']=report['length']
                j['best_length']=report['length'];j['best']=packer.placed;j['validation']=report;j['last_improvement']=time.time()
            if j['status']=='pausing':j['status']='paused'
            elif j['status']=='stopping':j['status']='stopped'
            elif j['elapsed']>=j['settings']['budget_seconds'] or j['settings']['mode']=='quick':j['status']='completed'
        store.mutate(jid,commit)
    except Exception as exc:
        log.exception('Optimization failed: %s',jid)
        def fail(j):j['status']='error';j['error']=str(exc);j['checkpoint']=None
        store.mutate(jid,fail)

def main():
    logging.basicConfig(level=logging.INFO)
    store.init()
    lock=open(store.DATA/'worker.lock','w')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit('Yalnızca bir worker başlatılabilir.')
    # Durable partial candidate + deterministic seed survives process restart.
    for j in store.all_jobs():
        if j['status']=='pausing':store.mutate(j['id'],lambda a:a.update(status='paused'))
        elif j['status']=='stopping':store.mutate(j['id'],lambda a:a.update(status='stopped',checkpoint=None))
    while True:
        jobs=[j for j in reversed(store.all_jobs()) if j['status']=='running']
        if not jobs:time.sleep(.5);continue
        for job in jobs:run_attempt(job['id'])

if __name__=='__main__':main()
