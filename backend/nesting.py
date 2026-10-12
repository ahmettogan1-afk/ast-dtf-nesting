"""True-shape strip packing, multi-start bottom-left and angle/order search.

No optimality guarantee. Bounding boxes are broad phase ONLY. Every accepted
candidate passes guarded polygon distance checks. A deterministic seed per
attempt and durable partial placement make pause/resume reproducible.
"""
import math
import random
from collections import defaultdict
from shapely import affinity
from .vector_io import local_geometry
from .geometry import parts

EPS=.002
class SpatialIndex:
    def __init__(self,gap,cell=60):self.cells=defaultdict(set);self.items=[];self.cell=cell;self.gap=gap
    def keys(self,b,extra=0):
        x0,y0,x1,y1=b;s=self.cell
        for x in range(math.floor((x0-extra)/s),math.floor((x1+extra)/s)+1):
            for y in range(math.floor((y0-extra)/s),math.floor((y1+extra)/s)+1):yield x,y
    def add(self,g):
        idx=len(self.items);self.items.append(g)
        for k in self.keys(g.bounds):self.cells[k].add(idx)
    def conflicts(self,g):
        ids=set()
        for k in self.keys(g.bounds,self.gap+EPS):ids.update(self.cells.get(k,()))
        return [self.items[i] for i in ids if g.distance(self.items[i])<self.gap+EPS*.25 or g.intersects(self.items[i])]

class Packer:
    def __init__(self,assets,settings,seed=0,attempt=0):
        self.assets=assets;self.settings=settings;self.attempt=attempt;self.rng=random.Random(seed)
        self.base={aid:local_geometry(a).simplify(.06,preserve_topology=True).buffer(.061,quad_segs=8,join_style=2) for aid,a in assets.items()};self.cache={}
        self.margin=settings['margin'];self.gap=settings['gap'];self.width=settings['width']
        self.index=SpatialIndex(self.gap);self.xanchors={self.margin};self.edgeanchors={self.margin};self.placed=[];self.top=self.margin
        instances=[(aid,i) for aid,a in assets.items() for i in range(a['quantity'])]
        priorities={aid:self.rng.uniform(.6,1.4) if attempt else 1 for aid in assets}
        self.order=sorted(instances,key=lambda it:-self.base[it[0]].area*priorities[it[0]])

    def angles(self,aid):
        if self.assets[aid]['rotation_locked']:return [0.]
        if self.attempt==0:return [0.,90.]
        # Full circle coverage through multi-start; later attempts refine 0.25°.
        offset=(self.attempt*13)%90
        if self.attempt%3==0:offset+=(self.attempt%4)*.25
        return list(dict.fromkeys([0.,90.,float(offset),float((offset+90)%360),float((offset+180)%360),float((offset+270)%360)]))

    def shape(self,aid,angle):
        key=aid,angle
        if key not in self.cache:
            g=affinity.rotate(self.base[aid],angle,origin=(0,0));x,y,xx,yy=g.bounds
            self.cache[key]=(affinity.translate(g,-x,-y),x,y,xx-x,yy-y)
        return self.cache[key]

    def add(self,p):
        g,ox,oy,w,h=self.shape(p['asset_id'],p['angle'])
        placed=affinity.translate(g,p['x']+ox,p['y']+oy)
        self.index.add(placed);self.placed.append(p);self.top=max(self.top,placed.bounds[3])
        self.edgeanchors.add(round(placed.bounds[2]+self.gap+EPS,4))
        coords=[]
        for poly in parts(placed):
            c=list(poly.exterior.coords);coords.extend(c[::max(1,len(c)//12)])
        for x,y in coords:self.xanchors.add(round(x+self.gap+EPS,4));self.xanchors.add(round(x-self.gap-EPS,4))
        self.xanchors={x for x in self.xanchors if self.margin<=x<=self.width-self.margin}

    def next(self,interrupt=lambda:False):
        aid,i=self.order[len(self.placed)]
        best=None;keybest=None
        for angle in self.angles(aid):
            g,ox,oy,w,h=self.shape(aid,angle)
            right=self.width-self.margin-w
            if right<self.margin-1e-6:continue
            xs={self.margin,right}
            for anchor in self.xanchors:
                if self.margin<=anchor<=right:xs.add(anchor)
                if self.margin<=anchor-w<=right:xs.add(anchor-w)
            # Include uniformly sampled offsets to reach exterior concavities.
            if self.attempt:xs.update(self.margin+(right-self.margin)*n/12 for n in range(13))
            xs=sorted(xs)
            limit=24 if self.attempt==0 else 48
            if len(xs)>limit:
                # Preserve edge/contact candidates plus deterministic spread.
                xs=sorted(set(xs[:limit//2]+[xs[round(k*(len(xs)-1)/(limit//2-1))] for k in range(limit//2)]))
            # Never discard simple right-edge contacts when sampling detailed
            # lettering vertices; they provide an efficient valid baseline.
            xs=sorted(set(xs)|set(sorted(x for x in self.edgeanchors if self.margin<=x<=right)[:limit]))
            for x in xs:
                y=self.margin
                for _ in range(len(self.placed)+2):
                    if interrupt():return None
                    if keybest and max(self.top,y+h)>keybest[0]+1e-7:break
                    candidate=affinity.translate(g,x,y)
                    collisions=self.index.conflicts(candidate)
                    if not collisions:
                        key=(max(self.top,y+h),y+h,y,x)
                        if keybest is None or key<keybest:
                            keybest=key;best={'asset_id':aid,'instance':f'{aid}:{i}','x':x-ox,'y':y-oy,'angle':angle}
                        break
                    # Jump past blockers. Concavity entries at starting y and
                    # sampled x remain usable; not an exact NFP optimizer.
                    y=max(c.bounds[3] for c in collisions)+self.gap+EPS
        if best is None:raise ValueError(f"{self.assets[aid]['name']} kullanılabilir film genişliğine sığmıyor.")
        self.add(best);return best

    def finish(self):
        while len(self.placed)<len(self.order):self.next()
        return self.placed
