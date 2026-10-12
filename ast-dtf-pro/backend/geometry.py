"""Vector-only SVG geometry. All returned coordinates are millimetres, y down.

Fail closed for unknown paint operations. Curves use bounded subdivision;
geometry is enlarged, never simplified inward. Closed holes are reserved only
AFTER the group union, retaining open concavities and all disconnected pieces.
"""
import math
import re
import numpy as np
from defusedxml import ElementTree as ET
from shapely.geometry import Polygon, MultiPolygon, LineString, GeometryCollection, box
from shapely.ops import unary_union, polygonize
from shapely import affinity, make_valid
from svgpathtools import parse_path, Line, CubicBezier, QuadraticBezier, Arc

TOL = 0.015
GUARD = 0.04
MAX_POINTS = 180000
NUM = r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?'

def tag(e):
    return e.tag.split('}')[-1]

def number(v, default=0):
    if v is None:
        return default
    if not re.fullmatch(NUM, str(v).strip()):
        raise ValueError(f'Desteklenmeyen sayısal SVG değeri: {v}')
    f = float(v)
    if not math.isfinite(f) or abs(f) > 1e8:
        raise ValueError('SVG koordinatı izin verilen sınırı aşıyor.')
    return f

def unit_mm(v):
    m = re.fullmatch(r'\s*(' + NUM + r')\s*(mm|cm|in|pt|pc|px)?\s*', v or '')
    if not m:
        raise ValueError('SVG fiziksel genişlik/yüksekliği mm, cm, in, pt veya px olmalı.')
    return float(m[1]) * {'mm':1,'cm':10,'in':25.4,'pt':25.4/72,'pc':25.4/6,'px':25.4/96,None:25.4/96}[m[2]]

def matrix(s=''):
    m = np.eye(3)
    rest = s
    for match in re.finditer(r'([a-zA-Z]+)\s*\(([^)]*)\)', s):
        rest = rest.replace(match[0], '', 1)
        name = match[1]
        values = [float(x) for x in re.findall(NUM, match[2])]
        a = np.eye(3)
        if name == 'matrix' and len(values) == 6:
            aa,b,c,d,e,f = values
            a = np.array([[aa,c,e],[b,d,f],[0,0,1.]])
        elif name == 'translate' and len(values) in (1,2):
            a[0,2] = values[0]; a[1,2] = values[1] if len(values)>1 else 0
        elif name == 'scale' and len(values) in (1,2):
            a[0,0] = values[0]; a[1,1] = values[-1]
        elif name == 'rotate' and len(values) in (1,3):
            t = math.radians(values[0]);c,sn = math.cos(t),math.sin(t)
            a[:2,:2] = [[c,-sn],[sn,c]]
            if len(values)==3:
                cx,cy=values[1:];a[:2,2]=[cx-c*cx+sn*cy,cy-sn*cx-c*cy]
        elif name in ('skewX','skewY') and len(values)==1:
            a[0 if name=='skewX' else 1,1 if name=='skewX' else 0] = math.tan(math.radians(values[0]))
        else:
            raise ValueError(f'Desteklenmeyen SVG dönüşümü: {name}')
        if not np.isfinite(a).all():
            raise ValueError('Geçersiz SVG dönüşümü.')
        m = m @ a
    if rest.strip(' ,\t\r\n'):
        raise ValueError('SVG dönüşümü çözümlenemedi.')
    return m

def apply(g,m):
    return affinity.affine_transform(g,[m[0,0],m[0,1],m[1,0],m[1,1],m[0,2],m[1,2]])

def parts(g):
    if isinstance(g,Polygon): return [g]
    if hasattr(g,'geoms'): return [p for x in g.geoms for p in parts(x)]
    return []

def reserve_holes(g):
    return unary_union([Polygon(p.exterior) for p in parts(make_valid(g))])

def line_distance(p,a,b):
    if a==b: return abs(p-a)
    t=max(0,min(1,((p-a).real*(b-a).real+(p-a).imag*(b-a).imag)/abs(b-a)**2))
    return abs(p-(a+t*(b-a)))

def flatten(segment,tol,depth=0):
    if isinstance(segment,Line): return [segment.start,segment.end]
    if isinstance(segment,Arc):
        radius=max(abs(segment.radius.real),abs(segment.radius.imag))
        delta=abs(math.radians(segment.delta))
        n=max(2,math.ceil(delta/math.sqrt(max(1e-12,8*tol/max(radius,1e-9)))))
        if n>MAX_POINTS: raise ValueError('SVG yayı çok karmaşık.')
        return [segment.point(i/n) for i in range(n+1)]
    controls=([segment.control1,segment.control2] if isinstance(segment,CubicBezier) else [segment.control])
    if max(line_distance(p,segment.start,segment.end) for p in controls)<=tol:
        return [segment.start,segment.end]
    if depth>=24: raise ValueError('Eğri toleransı güvenle hesaplanamadı.')
    a,b=segment.split(.5)
    return flatten(a,tol,depth+1)[:-1]+flatten(b,tol,depth+1)

def winding(point, ring):
    x,y=point;w=0
    for (x1,y1),(x2,y2) in zip(ring,ring[1:]):
        cross=(x2-x1)*(y-y1)-(x-x1)*(y2-y1)
        if y1<=y<y2 and cross>0:w+=1
        if y2<=y<y1 and cross<0:w-=1
    return w

def fill_rings(rings,rule):
    edges=[]
    for r in rings:
        if len(r)>=3:
            if r[-1]!=r[0]:r=r+[r[0]]
            edges.append(r)
    if not edges:return GeometryCollection()
    faces=polygonize(unary_union([LineString(r) for r in edges]))
    kept=[]
    for face in faces:
        p=face.representative_point();w=sum(winding((p.x,p.y),r) for r in edges)
        if (w%2!=0 if rule=='evenodd' else w!=0): kept.append(face)
    return unary_union(kept)

class SVGGeometry:
    def __init__(self,data, pdf_points=False):
        if len(data)>25*1024*1024:raise ValueError('SVG 25 MB sınırını aşıyor.')
        self.root=ET.fromstring(data)
        if tag(self.root)!='svg':raise ValueError('Geçerli bir SVG kökü bulunamadı.')
        self.ids={e.get('id'):e for e in self.root.iter() if e.get('id')}
        self.count=0;self.white_background=False
        allowed={'svg','g','defs','path','rect','circle','ellipse','line','polyline','polygon','use','clipPath','title','desc','metadata'}
        for e in self.root.iter():
            if tag(e) not in allowed:
                raise ValueError(f'SVG özelliği desteklenmiyor: {tag(e)}. Metni kontura çevirin; efektleri kaldırın.')
            for k,v in e.attrib.items():
                key=k.split('}')[-1]
                if key.lower().startswith('on') or key in ('filter','mask','class','vector-effect','marker-start','marker-mid','marker-end'):
                    raise ValueError(f'Güvensiz veya desteklenmeyen SVG özelliği: {key}')
                if key in ('href',) and not v.startswith('#'):
                    raise ValueError('SVG dış kaynak bağlantıları kabul edilmez.')
                if key=='visibility' and v!='visible':raise ValueError('SVG visibility geçişi desteklenmiyor; gizli nesneleri kaldırın.')
                if 'url(' in v and not re.fullmatch(r'url\(#[\w.:-]+\)',v.strip()):
                    raise ValueError('SVG dış kaynak veya karmaşık boya referansı kabul edilmez.')
        vb=[float(x) for x in re.findall(NUM,self.root.get('viewBox',''))]
        if pdf_points:
            self.width=float(self.root.get('width'))*25.4/72
            self.height=float(self.root.get('height'))*25.4/72
        else:
            self.width=unit_mm(self.root.get('width'));self.height=unit_mm(self.root.get('height'))
        if not (0<self.width<=10000 and 0<self.height<=10000):raise ValueError('SVG sayfa ölçüsü 0–10000 mm aralığında olmalı.')
        if not vb:vb=[0,0,self.width*96/25.4,self.height*96/25.4]
        if len(vb)!=4 or vb[2]<=0 or vb[3]<=0:raise ValueError('Geçersiz SVG viewBox.')
        sx,sy=self.width/vb[2],self.height/vb[3]
        par=self.root.get('preserveAspectRatio','xMidYMid meet').strip()
        if par!='none':
            if par not in ('xMidYMid meet','xMidYMid'):raise ValueError('SVG preserveAspectRatio yalnızca none veya xMidYMid meet olabilir.')
            sx=sy=min(sx,sy)
        self.base=np.array([[sx,0,(self.width-vb[2]*sx)/2-vb[0]*sx],[0,sy,(self.height-vb[3]*sy)/2-vb[1]*sy],[0,0,1.]])

    def contours(self,e,tol):
        t=tag(e);get=lambda k,d=0:number(e.get(k),d)
        if t=='path':
            path=parse_path(e.get('d',''));rings=[]
            for sub in path.continuous_subpaths():
                pts=[]
                for seg in sub:
                    pts+=flatten(seg,tol)[:-1]
                if len(sub):pts.append(sub[-1].end)
                rings.append([(p.real,p.imag) for p in pts])
        elif t=='rect':
            x,y,w,h=get('x'),get('y'),get('width'),get('height')
            if w<0 or h<0:raise ValueError('Negatif SVG dikdörtgen ölçüsü.')
            # Rounded rectangle is conservatively reserved as its full rectangle.
            rings=[[(x,y),(x+w,y),(x+w,y+h),(x,y+h),(x,y)]]
        elif t in ('circle','ellipse'):
            x,y=get('cx'),get('cy');rx=get('r') if t=='circle' else get('rx');ry=rx if t=='circle' else get('ry')
            n=max(16,math.ceil(2*math.pi/math.sqrt(max(1e-12,8*tol/max(rx,ry,1e-9)))))
            if n>MAX_POINTS:raise ValueError('SVG elipsi çok karmaşık.')
            rings=[[(x+rx*math.cos(2*math.pi*i/n),y+ry*math.sin(2*math.pi*i/n)) for i in range(n+1)]]
        elif t=='line':rings=[[(get('x1'),get('y1')),(get('x2'),get('y2'))]]
        else:
            values=[float(v) for v in re.findall(NUM,e.get('points',''))]
            if len(values)%2:raise ValueError('Geçersiz SVG nokta listesi.')
            ring=list(zip(values[::2],values[1::2]))
            if t=='polygon' and ring:ring.append(ring[0])
            rings=[ring]
        self.count+=sum(map(len,rings))
        if self.count>MAX_POINTS:raise ValueError('Dosya geometri karmaşıklığı sınırını aşıyor. Logoları ayrı yükleyin.')
        return rings

    def walk(self,e,m,style,stack=(),clipmode=False,root=False):
        t=tag(e)
        if t in ('defs','title','desc','metadata') or (t=='clipPath' and not clipmode):return GeometryCollection()
        if t=='svg' and not root:raise ValueError('İç içe SVG viewport desteklenmiyor.')
        st=dict(style)
        supported={'fill','fill-rule','clip-rule','stroke','stroke-width','stroke-linecap','stroke-linejoin','stroke-miterlimit','stroke-dasharray','stroke-dashoffset','opacity','fill-opacity','stroke-opacity','display','visibility','clip-path'}
        for entry in e.get('style','').split(';'):
            if not entry.strip():continue
            if ':' not in entry:raise ValueError('SVG style çözümlenemedi.')
            k,v=entry.split(':',1);k=k.strip();v=v.strip()
            if k not in supported:raise ValueError(f'Desteklenmeyen SVG stili: {k}')
            st[k]=v
        for k in supported:
            if e.get(k) is not None:st[k]=e.get(k)
        if st.get('display')=='none' or st.get('visibility') in ('hidden','collapse') or number(st.get('opacity'),1)==0:return GeometryCollection()
        m=m @ matrix(e.get('transform',''))
        if abs(np.linalg.det(m[:2,:2]))<1e-14:return GeometryCollection()
        if t=='use':
            ref=e.get('href') or e.get('{http://www.w3.org/1999/xlink}href','')
            if not ref.startswith('#') or ref[1:] not in self.ids:raise ValueError('Çözümlenemeyen SVG use referansı.')
            if ref in stack or len(stack)>24:raise ValueError('Döngüsel/derin SVG referansı.')
            tr=np.eye(3);tr[:2,2]=[number(e.get('x')),number(e.get('y'))]
            childstyle={k:v for k,v in st.items() if k not in ('clip-path','opacity')}
            g=self.walk(self.ids[ref[1:]],m@tr,childstyle,stack+(ref,),clipmode)
        elif t in ('g','svg','clipPath'):
            if t=='clipPath' and e.get('clipPathUnits','userSpaceOnUse')!='userSpaceOnUse':raise ValueError('objectBoundingBox clipping desteklenmiyor.')
            childstyle={k:v for k,v in st.items() if k not in ('clip-path','opacity')}
            g=unary_union([self.walk(c,m,childstyle,stack,clipmode) for c in e])
        else:
            norm=float(np.linalg.norm(m[:2,:2],2));rings=self.contours(e,TOL/max(norm,1e-12))
            pieces=[]
            if clipmode or (st.get('fill','black')!='none' and number(st.get('fill-opacity'),1)>0):
                if st.get('fill','').startswith('url('):raise ValueError('Gradient/pattern dolgu desteklenmiyor.')
                pieces.append(fill_rings(rings,st.get('clip-rule' if clipmode else 'fill-rule','nonzero')))
            if not clipmode and st.get('stroke','none')!='none' and number(st.get('stroke-opacity'),1)>0:
                width=number(st.get('stroke-width'),1)
                if width==0:raise ValueError('Sıfır genişlikte hairline kontur desteklenmiyor; genişlik atayın.')
                join={'round':1,'miter':2,'bevel':3}.get(st.get('stroke-linejoin','miter'))
                cap={'round':1,'butt':2,'square':3}.get(st.get('stroke-linecap','butt'))
                if join is None or cap is None:raise ValueError('Desteklenmeyen kontur birleşimi.')
                pieces += [LineString(r).buffer(width/2,quad_segs=32,join_style=join,cap_style=cap,mitre_limit=number(st.get('stroke-miterlimit'),4)) for r in rings if len(r)>=2]
            g=apply(unary_union(pieces),m)
            if st.get('fill','').lower() in ('#fff','#ffffff','white','rgb(255,255,255)') and g.area>self.width*self.height*.94:
                self.white_background=True
        clip=st.get('clip-path')
        if clip and clip!='none':
            match=re.fullmatch(r'url\(#([\w.:-]+)\)',clip)
            if not match or match[1] not in self.ids:raise ValueError('Geçersiz clipping referansı.')
            ref='#'+match[1]
            if ref in stack:raise ValueError('Döngüsel clipping referansı.')
            cg=self.walk(self.ids[match[1]],m,{},stack+(ref,),True)
            g=g.intersection(cg)
        return g

    def geometry(self,guarded=True):
        self.count=0
        g=self.walk(self.root,self.base,{},root=True).intersection(box(0,0,self.width,self.height))
        g=unary_union(parts(make_valid(g)))
        if g.is_empty or g.area<1e-8:raise ValueError('Baskı yapılabilir vektör bulunamadı.')
        # Reserve enclosed holes, retaining concavities. Guard covers flattening
        # and SVG serialization rounding. Never use this geometry as artwork.
        return reserve_holes(g.buffer(GUARD,quad_segs=16,join_style=2)) if guarded else g
