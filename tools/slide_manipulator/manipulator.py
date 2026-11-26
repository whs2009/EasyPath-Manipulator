import ctypes as C
import math,os,sys,threading
from pathlib import Path
from collections import OrderedDict
from PIL import Image,ImageDraw
import numpy as np
from shapely import Point
from shapely.geometry import Polygon
from project import Project,Frame,Object,probe,document,generate,save,bounds,geom,matrix
from engine import Session

class Editor:
    def __init__(self,hospital):
        self.hospital=hospital;self.p=Project();self.frame=0;self.src=-1;self.sel=-1
        self.view=(0,0,1);self.dim=(700,500);self.cache=OrderedDict()
        self.srgb=True;self.bits=8;self.loss=5;self.distance=4;self.facts='';self.points=[]
        self.cancel=threading.Event();self.worker=None;self.status='';self.dirty=False
    @property
    def f(self):return self.p.frames[self.frame]
    def pick(self):
        if not 0<=self.sel<len(self.f.objects):raise ValueError('Select a placement first.')
        return self.f.objects[self.sel]
    def fit(self):
        if not any(f.objects for f in self.p.frames):self.view=(0,0,1);return
        x,y,r,b=bounds(self.p);w,h=self.dim
        k=min((w-24)/max(r-x,1),(h-24)/max(b-y,1));self.view=((w-(x+r)*k)/2,(h-(y+b)*k)/2,k)
    def thumb(self,s,z):
        key=(s.path,s.mtime,z)
        if key not in self.cache:
            reader=Session(self.hospital)
            try:
                dims,_=reader.open(s.path)
                if z>=dims[2]:raise ValueError('Focal plane unavailable for preview.')
                zoom=max(-12,min(12,12-math.ceil(math.log2(max(1,max(dims[:2])/512)))))
                step=2**(12-zoom)
                rgb=reader.render(0,0,zoom,math.ceil(dims[0]/step),math.ceil(dims[1]/step),z)
                self.cache[key]=Image.fromarray(rgb)
            finally:reader.close()
            if len(self.cache)>32:self.cache.popitem(last=False)
        self.cache.move_to_end(key);return self.cache[key]
    def coords(self,o,x,y):
        ax,ay,k=self.view
        return (np.linalg.inv(matrix(o,self.p.sources[o.src]))@[(x-ax)/k,(y-ay)/k,1])[:2]
    def render(self,w,h):
        if self.dim!=(w,h):self.dim=(w,h);self.fit()
        base=Image.new('RGB',(w,h),(57,61,66));ax,ay,k=self.view
        screen=np.array([[k,0,ax],[0,k,ay],[0,0,1.]])
        for fi,opacity in ([(0,self.f.base_opacity/10),(self.frame,self.f.active_opacity/10)] if self.frame else [(0,1)]):
            layer=base.copy();outline=None
            for i,o in enumerate(self.p.frames[fi].objects):
                s=self.p.sources[o.src];im=self.thumb(s,o.plane);a=screen@matrix(o,s)
                inv=np.diag([im.width/s.width,im.height/s.height,1])@np.linalg.inv(a)
                tile=im.transform((w,h),Image.Transform.AFFINE,inv[:2].flatten(),Image.Resampling.BILINEAR)
                coords=[tuple((a@[x,y,1])[:2]) for x,y in geom(o,s).exterior.coords]
                mask=Image.new('L',(w,h));ImageDraw.Draw(mask).polygon(coords,fill=255)
                layer.paste(tile,mask=mask)
                if fi==self.frame and i==self.sel:outline=coords
            base=Image.blend(base,layer,opacity)
            if outline:
                draw=ImageDraw.Draw(base);draw.line(outline,fill='#04cfc2',width=2)
                if len(self.points):
                    o=self.pick();a=screen@matrix(o,self.p.sources[o.src])
                    pts=[tuple((a@[x,y,1])[:2]) for x,y in self.points]
                    if len(pts)>1:draw.line(pts,fill='orange',width=2)
                    for x,y in pts:draw.ellipse((x-2,y-2,x+2,y+2),fill='orange')
        return base
    def act(self,cmd,s='',a=0,b=0):
        if cmd=='status':return self.status
        if cmd=='busy':return str(int(self.worker is not None and self.worker.is_alive()))
        if cmd=='cancel':self.cancel.set();return ''
        if cmd=='dirty':return str(int(self.dirty))
        if self.act('busy')=='1':raise ValueError('Wait for export or cancel it.')
        if cmd=='sources':return '\n'.join(Path(q.path).name for q in self.p.sources)
        if cmd=='frames':return '\n'.join(q.name for q in self.p.frames)
        if cmd=='objects':return '\n'.join(f'{Path(self.p.sources[q.src].path).name}  [plane {q.plane+1}]' for q in self.f.objects)
        if cmd=='state':
            o=self.pick() if self.sel>=0 else None
            return ' '.join(map(str,[self.src,self.frame,self.sel,len(self.p.frames),self.p.sources[self.src].planes if self.src>=0 else 1,
                 o.angle if o else 0,o.scale if o else 1,self.f.base_opacity,self.f.active_opacity]))
        if cmd=='srgb':self.srgb=bool(a);return ''
        if cmd=='source':self.src=int(a);return ''
        if cmd=='frame':self.frame=int(a);self.sel=-1;self.points=[];return ''
        if cmd=='object':self.sel=int(a);self.points=[];return ''
        if cmd=='fit':self.fit();return ''
        if cmd=='save':save(self.p,s);self.dirty=False;return ''
        if cmd=='load':
            p=document(s)
            for q in p.sources:
                if probe(q.path,self.hospital,self.srgb)!=q:raise ValueError('Source changed since project was saved.')
            self.p=p;self.src=0 if p.sources else -1;self.frame=0;self.sel=-1;self.points=[];self.cache.clear();self.fit();self.dirty=False;return ''
        if cmd=='input':
            q=probe(s,self.hospital,self.srgb)
            if q in self.p.sources:self.src=self.p.sources.index(q);return ''
            if len(self.p.sources)>=128:raise ValueError('Maximum 128 source slides.')
            self.thumb(q,0);self.p.sources.append(q);self.src=len(self.p.sources)-1
        elif cmd=='place':
            if self.src<0:raise ValueError('Select an input slide.')
            q=self.p.sources[self.src];z=int(a)-1
            if not 0<=z<q.planes or len(self.f.objects)>=256:raise ValueError('Invalid focal plane or placement limit.')
            self.thumb(q,z);self.f.objects.append(Object(src=self.src,plane=z,x=q.width/2,y=q.height/2));self.sel=len(self.f.objects)-1;self.points=[];self.fit()
        elif cmd=='addframe':
            if len(self.p.frames)>=20:raise ValueError('Maximum 20 frames including the basal layer.')
            self.frame+=1;self.p.frames.insert(self.frame,Frame(name=s or f'Frame {self.frame}'));self.sel=-1;self.points=[]
        elif cmd=='name':self.f.name=s
        elif cmd=='deleteframe':
            if not self.frame:raise ValueError('The basal layer cannot be deleted.')
            self.p.frames.pop(self.frame);self.frame-=1;self.sel=-1;self.points=[];self.fit()
        elif cmd=='order':
            n=self.frame+int(a)
            if min(self.frame,n)<1 or n>=len(self.p.frames):raise ValueError('Cannot move this frame.')
            self.p.frames[self.frame],self.p.frames[n]=self.p.frames[n],self.f;self.frame=n
        elif cmd=='remove':self.pick();self.f.objects.pop(self.sel);self.sel=-1;self.points=[]
        elif cmd=='hit':
            self.sel=next((i for i,o in reversed(list(enumerate(self.f.objects))) if geom(o,self.p.sources[o.src]).covers(Point(self.coords(o,a,b)))),-1)
            self.points=[];return ''
        elif cmd=='drag':
            if self.sel<0:return ''
            o=self.pick();o.x+=a/self.view[2];o.y+=b/self.view[2]
        elif cmd=='flip':o=self.pick();o.mirror_x=not o.mirror_x
        elif cmd=='flop':o=self.pick();o.mirror_y=not o.mirror_y
        elif cmd=='pose':o=self.pick();o.angle=a;o.scale=b
        elif cmd=='opacity':self.f.base_opacity=int(a);self.f.active_opacity=int(b)
        elif cmd=='vertex':
            o=self.pick();pt=tuple(map(float,self.coords(o,a,b)));q=self.p.sources[o.src]
            if not 0<=pt[0]<=q.width or not 0<=pt[1]<=q.height:raise ValueError('Click inside the selected slide.')
            if len(self.points)>=4096:raise ValueError('Polygon point limit reached.')
            self.points.append(pt);return ''
        elif cmd=='crop':
            o=self.pick()
            if len(self.points)<3:raise ValueError('Choose at least three crop vertices.')
            candidate=o.model_copy(update={'crop':self.points.copy()});geom(candidate,self.p.sources[o.src]);o.crop=candidate.crop;self.points=[]
        elif cmd=='resetcrop':self.pick().crop=[];self.points=[]
        elif cmd=='clear':self.points=[];return ''
        elif cmd=='facts':self.facts=s;return ''
        elif cmd=='settings':self.bits=int(a);self.loss=int(b);self.distance=int(s);return ''
        elif cmd=='export':
            model=self.p.model_copy(deep=True);self.cancel.clear();self.status='Exporting...'
            if Path(s).suffix.lower()=='.dcm' and not self.facts:raise ValueError('Choose verified DICOM facts first.')
            def check():
                if self.cancel.is_set():raise ValueError('Export cancelled.')
            def run():
                try:
                    generate(model,s,hospital=self.hospital,srgb=self.srgb,bits=self.bits,loss=self.loss,distance=self.distance,facts=self.facts,check=check)
                    self.status='Saved: '+s
                except Exception as exc:self.status='Export failed: '+str(exc)
            self.worker=threading.Thread(target=run);self.worker.start();return ''
        else:raise ValueError('Unknown command.')
        self.dirty=True;return ''

def main(argv):
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
    hospital=False
    sys._easypath_converter=bool(getattr(sys,'frozen',False))
    if argv[:1]==['--check-project'] and len(argv)==3:
        import json
        with open(argv[2],encoding='utf-8') as f:req=json.load(f)
        generate(document(argv[1]),hospital=hospital,**req);return 0
    if len(argv)==2 and argv[0]=='--check-detail':
        from workspace import Workspace
        e=Workspace(hospital);reader=Session(hospital)
        try:
            e.act('input',argv[1]);e.act('whole');reader.open(argv[1])
            if reader.dims[:2]!=(1536,768) or reader.dims[5]!=1:return 66
            rgb=reader.render(750,330,12,141,101,0)
            for out in (False,True):
                if out:e.act('out_whole')
                e.act('out_open' if out else 'open','source' if out else 'align')
                view=e.output_editor if out else e;view.camera=(-750,-330,1);view.size=(141,101);view.sel=-1
                actual=np.asarray(e.paint('source' if out else 'align',141,101))
                if not np.array_equal(actual[:36],rgb[:36]) or not e.pixels.patches:return 67
                e.act('close_view')
            return 0
        finally:e.close_view();reader.close()
    check_ui=len(argv)==3 and argv[0]=='--check-mapping'
    if not check_ui and argv not in ([],['--gui-smoke']):return 2
    from workspace import Workspace
    ed=Workspace(hospital);I=C.c_int;P=C.c_void_p;S=C.c_char_p;D=C.c_double
    call=C.CFUNCTYPE(I,S,S,D,D,P,I);paint=C.CFUNCTYPE(I,I,I,I,P)
    @call
    def command(cmd,arg,a,b,out,n):
        rc=0
        try:msg=ed.act(cmd.decode(),arg.decode(),a,b)
        except Exception as e:rc=1;msg=str(e)
        data=msg.encode('utf-8','replace')[:n-1]+b'\0';C.memmove(out,data,len(data));return rc
    @paint
    def render(kind,w,h,out):
        try:
            if min(w,h)<32 or w*h>8_388_608:raise ValueError('Canvas dimensions unsupported.')
            data=ed.paint(('preview','source','align','outpreview')[kind],w,h).tobytes();C.memmove(out,data,len(data));return 0
        except Exception as e:ed.status=str(e);return 1
    dll=root/('manipulator_ui.dll' if os.name=='nt' else 'libmanipulator_ui.dylib' if sys.platform=='darwin' else 'libmanipulator_ui.so')
    ui=C.CDLL(str(dll))
    try:
        if check_ui:
            ed.act('srgb','',1);ed.act('input',argv[1])
            ui.manipulator_check.argtypes=[call,paint,S];return ui.manipulator_check(command,render,os.fsencode(argv[2]))
        ui.manipulator_show.argtypes=[call,paint,I];return ui.manipulator_show(command,render,bool(argv))
    finally:ed.close_view()
if __name__=='__main__':sys.exit(main(sys.argv[1:]))
