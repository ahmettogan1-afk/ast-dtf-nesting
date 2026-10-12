"""Independent acceptance path: no candidate index, score, or optimizer cache."""
import math
from collections import Counter
from shapely import STRtree
from .vector_io import placed_geometry

def validate(job,assets,placements):
    errors=[];settings=job['settings'];width=settings['width'];margin=settings['margin'];gap=settings['gap']
    wanted=Counter({a['id']:a['quantity'] for a in assets.values()})
    actual=Counter(p.get('asset_id') for p in placements)
    if wanted!=actual:errors.append('İstenen adetler ile yerleştirilen adetler farklı.')
    ids=[p.get('instance') for p in placements]
    if len(set(ids))!=len(ids):errors.append('Tekrarlanan kopya kimliği var.')
    geometries=[]
    for p in placements:
        a=assets.get(p.get('asset_id'))
        if not a:errors.append('Bilinmeyen logo.');continue
        if not all(math.isfinite(p.get(k,float('nan'))) for k in ('x','y','angle')):errors.append('Geçersiz koordinat.');continue
        if a['rotation_locked'] and abs(p['angle']%360)>1e-7:errors.append('Döndürme kilidi ihlali.')
        g=placed_geometry(a,p)
        if not g.is_valid or g.is_empty:errors.append('Geçersiz baskı geometrisi.');continue
        x0,y0,x1,y1=g.bounds
        if x0<margin-1e-6 or x1>width-margin+1e-6 or y0<margin-1e-6:errors.append(f"Film sınırı ihlali: {p['instance']}")
        geometries.append((p['instance'],g))
    # Sweep on y only for broad phase; exact distance uses fresh GEOS geometry.
    ordered=sorted(geometries,key=lambda v:v[1].bounds[1]);active=[];minimum=None
    for iid,g in ordered:
        b=g.bounds;active=[q for q in active if q[1].bounds[3]+gap+1e-6>=b[1]]
        for oid,other in active:
            ob=other.bounds
            if ob[2]+gap<b[0] or b[2]+gap<ob[0]:continue
            d=g.distance(other)
            minimum=d if minimum is None else min(minimum,d)
            if g.intersection(other).area>1e-8 or d<gap-1e-6:errors.append(f'Mesafe/çakışma ihlali: {iid} / {oid} ({d:.4f} mm)')
        active.append((iid,g))
    if len(geometries)>1:
        values=[g for _,g in geometries]
        _,distances=STRtree(values).query_nearest(values,exclusive=True,return_distance=True)
        if len(distances):minimum=float(min(distances))
    length=max((g.bounds[3] for _,g in geometries),default=0)+margin
    return {'valid':not errors,'errors':errors[:100],'count':len(placements),'length':length,'minimum_distance_mm':minimum,'geometry_area':sum(g.area for _,g in geometries),'method':'independent GEOS exact-distance sweep on guarded vector geometry'}
