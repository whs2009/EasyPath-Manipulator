"""Mapping windows share a project, not a camera or a draft."""
import math
from pathlib import Path
from uuid import uuid4
import numpy as np
from PIL import Image, ImageDraw, ImageChops
from shapely import Point, Polygon, MultiPolygon, make_valid, union_all
from project import Frame,Object,Region,geom,matrix,transform
from manipulator import Editor
from types import SimpleNamespace as NS
from project import Layout,bounds
from viewport_pixels import ViewportPixels

def polygons(g):
    if isinstance(g,Polygon):return [g] if g.area else []
    return [p for part in getattr(g,'geoms',[]) for p in polygons(part)]
def parts(g):
    return [[list(p.exterior.coords),*(list(r.coords) for r in p.interiors)] for p in polygons(g)]
def title(i,f):
    return (('Basal layer' if not i else f'Layer {i}')+' ('+f.name+')') if f.name.strip() else ('Basal layer' if not i else f'Frame {i}')
def label(s):
    return ' '.join(str(s).splitlines())
def fitted(b,w,h):
    x,y,r,b=b;z=min(max(1,w-26)/max(1,r-x),max(1,h-26)/max(1,b-y))
    return (w-(r+x)*z)/2,(h-(b+y)*z)/2,z
def mask_draw(im,g,m,fill,outline=None):
    def points(r):
        pts=np.array(r.coords);return [tuple(v) for v in pts@m[:2,:2].T+m[:2,2]]
    d=ImageDraw.Draw(im);outline_rings=[]
    for p in polygons(g):
        for i,ring in enumerate([p.exterior,*p.interiors]):
            pts=points(ring);d.polygon(pts,fill=0 if i else fill);outline_rings.append(pts)
    if outline:
        for pts in outline_rings:outline.line(pts,fill='#18cea4',width=2)
    return outline_rings

class Workspace(Editor):
    def __init__(self,hospital):
        super().__init__(hospital)
        self.mode='';self.z=0;self.camera=None;self.size=None;self.draft=[];self.recording=False
        self.region_id=None;self.gesture=None;self.last_xy=None
        self.pixels=ViewportPixels(hospital);self.output_editor=None;self.editing_output=False
    def close_view(self):
        self.pixels.close()
        if self.editing_output and self.output_editor:self.output_editor.close_view()
        self.editing_output=False;self.mode='';self.camera=None;self.size=None;self.gesture=None
        self.recording=False;self.draft=[];self.region_id=None;self.last_xy=None
    def rows(self):
        return [(i,z) for i,s in enumerate(self.p.sources) for z in range(s.planes)]
    def regions(self):
        return [r for r in self.f.regions if (r.src,r.plane)==(self.src,self.z)]
    def setrow(self,i):
        rows=self.rows()
        if not 0<=i<len(rows):raise ValueError('Select a source plane.')
        self.src,self.z=rows[i]
    def layers(self,mode):
        if mode=='align' and self.frame:return [(self.p.frames[0],self.f.base_opacity/10),(self.f,self.f.active_opacity/10)]
        return [(self.f,1)]
    def extent(self,mode):
        if mode=='source':
            s=self.p.sources[self.src];return (0,0,s.width,s.height)
        boxes=[transform(geom(o,self.p.sources[o.src],f),matrix(o,self.p.sources[o.src])).bounds for f,_ in self.layers(mode) for o in f.objects]
        if not boxes:return (0,0,100,100)
        x,y,r,b=zip(*boxes);return min(x),min(y),max(r),max(b)
    def view_for(self,mode,w,h):
        if mode=='preview':return fitted(self.extent(mode),w,h)
        if self.camera is None or self.size!=(w,h):
            self.camera=fitted(self.extent(mode),w,h);self.size=(w,h)
        return self.camera
    def hit_region(self,x,y):
        p=Point(self.world(x,y))
        return next((r.id for r in reversed(self.regions()) if r.shape(self.p.sources[self.src]).covers(p)),None)
    def world(self,x,y):
        tx,ty,k=self.camera;return (x-tx)/k,(y-ty)/k
    def sample(self,x,y):
        s=self.p.sources[self.src];a,b=self.world(x,y)
        q=(min(s.width,max(0,a)),min(s.height,max(0,b)))
        if len(self.draft)<4096 and (not self.draft or math.dist(q,self.draft[-1])*self.camera[2]>=3):self.draft.append(q)
    def commit_crop(self,subtract=False):
        self.recording=False
        if len(self.draft)<3:raise ValueError('Draw at least three points.')
        g=union_all(polygons(make_valid(Polygon(self.draft))))
        if g.is_empty:raise ValueError('The crop has no area.')
        f=self.f.model_copy(deep=True);s=self.p.sources[self.src]
        matches=[r for r in f.regions if (r.src,r.plane)==(self.src,self.z) and r.shape(s).intersection(g).area>0]
        ids={r.id for r in matches}
        def adjusted(o,key,area):
            l,t,r,b=area.bounds;pv=((l+r)/2,(t+b)/2)
            x,y,_=matrix(o,s)@[*pv,1];o.pivot=pv;o.x=float(x);o.y=float(y);o.region=key
        if subtract:
            retained=[]
            for r in matches:
                shape=union_all(polygons(r.shape(s).difference(g)))
                if shape.is_empty:
                    f.objects=[o for o in f.objects if o.region!=r.id]
                else:
                    r.parts=parts(shape);r.shape(s);retained.append(r)
                    for o in f.objects:
                        if o.region==r.id:adjusted(o,r.id,shape)
            f.regions=[r for r in f.regions if r.id not in ids]+retained
            key=None
        else:
            area=union_all([g,*[r.shape(s) for r in matches]])
            key=matches[0].id if matches else uuid4().hex
            saved=Region(id=key,src=self.src,plane=self.z,parts=parts(area));saved.shape(s)
            f.regions=[r for r in f.regions if r.id not in ids]+[saved]
            for o in f.objects:
                if o.region in ids:adjusted(o,key,area)
        if sum(len(ring) for r in f.regions for part in r.parts for ring in part)>65536:raise ValueError('Frame crop point limit exceeded.')
        self.p.frames[self.frame]=f;self.sel=-1;self.region_id=key;self.draft=[];self.dirty=True
    def placement_mask(self,mask,s,z,m):return mask
    def image_for(self,s,z,m,size,clip,detail):
        return self.pixels.image(s,z,self.thumb(s,z),m,size,clip,detail)
    def output_view(self,reset=False):
        extent=bounds(self.p)
        data=self.p.output
        if data is not None and data.extent!=extent and not reset:
            raise ValueError('Merged slide bounds changed. Use Reset output layout to select regions again.')
        if not reset and data is None and self.output_editor and self.output_editor.f.extent==extent:return self.output_editor
        if reset or data is None:data=Layout(extent=extent)
        if reset or self.output_editor is None or self.output_editor.f is not data:
            if self.output_editor:self.output_editor.close_view()
            self.output_editor=OutputWorkspace(self,data)
        return self.output_editor
    def paint(self,mode,w,h):
        if mode=='outpreview':
            if self.p.output is None:return Image.new('RGB',(w,h),'#262a2a')
            return self.output_view().paint('preview',w,h)
        if self.editing_output and mode in ('source','align'):return self.output_editor.paint(mode,w,h)
        tx,ty,k=self.view_for(mode,w,h);m=np.array([[k,0,tx],[0,k,ty],[0.,0.,1.]])
        bg=Image.new('RGB',(w,h),'#262a2a')
        if mode=='source':
            s=self.p.sources[self.src];mask=Image.new('L',(w,h))
            from shapely import box
            mask_draw(mask,box(0,0,s.width,s.height),m,255)
            bg.paste(self.image_for(s,self.z,m,(w,h),mask.getbbox(),True),mask=mask)
            for r in self.regions():
                mask=Image.new('L',(w,h));rings=mask_draw(mask,r.shape(s),m,36)
                bg.paste('#00d995',mask=mask)
                draw=ImageDraw.Draw(bg)
                for pts in rings:draw.line(pts,fill='#ffd44d' if self.region_id==r.id else '#22d79a',width=2)
            if self.draft:
                pts=[(tx+x*k,ty+y*k) for x,y in self.draft];d=ImageDraw.Draw(bg)
                if len(pts)>1:d.line(pts,fill='#ffcd42',width=2)
                x,y=pts[-1];d.ellipse((x-2,y-2,x+2,y+2),fill='gold')
            return bg
        for f,opacity in self.layers(mode):
            if not opacity:continue
            layer=bg.copy();handles=[]
            for i,o in enumerate(f.objects):
                s=self.p.sources[o.src];g=geom(o,s,f);a=m@matrix(o,s)
                mask=Image.new('L',(w,h));rings=mask_draw(mask,g,a,255);clip=mask.getbbox()
                if clip:layer.paste(self.image_for(s,o.plane,a,(w,h),clip,mode=='align'),mask=self.placement_mask(mask,s,o.plane,a))
                if mode=='align' and f is self.f:handles.append((i,rings,tx+k*o.x,ty+k*o.y))
            bg=Image.blend(bg,layer,opacity);d=ImageDraw.Draw(bg)
            for i,rings,x,y in handles:
                if i==self.sel:
                    for pts in rings:d.line(pts,fill='#33d8b5',width=2)
                d.ellipse((x-6,y-6,x+6,y+6),fill='#f7b546',outline='#26302f',width=2)
        return bg
    def act(self,cmd,s='',a=0,b=0):
        if cmd in ('busy','dirty','status','cancel'):return super().act(cmd,s,a,b)
        if super().act('busy')=='1':raise ValueError('Export in progress.')
        if cmd=='titles':return '\n'.join(title(i,f) for i,f in enumerate(self.p.frames))
        if cmd=='srgb_value':return str(int(self.srgb))
        if cmd=='load':
            self.close_view();self.output_editor=None
        if cmd=='out_state':
            if not any(f.objects for f in self.p.frames):return '0 -1 0 0'
            if self.p.output and self.p.output.extent!=bounds(self.p):return '-1 -1 0 0'
            out=self.output_view();out.which=min(out.which,len(self.p.frames)-1)
            return f'1 {out.sel} {out.which} {len(out.f.objects)}'
        if cmd.startswith('out_'):
            op=cmd[4:];out=self.output_view(op=='reset')
            if op=='reset':self.p.output=out.f;self.dirty=True;return ''
            if op=='open':
                self.close_view();out.act('open',s);self.editing_output=True;return ''
            if op=='objects':return '\n'.join('Merged slide' if not o.region else 'Region '+o.region[:8] for o in out.f.objects)
            if op=='frame':out.which=max(0,min(len(self.p.frames)-1,int(a)));return ''
            return self.output_action(out,op,s,a,b)
        if self.editing_output:
            if cmd=='close_view':self.close_view();return ''
            if cmd=='display_index':return str(self.output_editor.which)
            if cmd=='display_plane':
                o=self.output_editor;o.which=max(0,min(len(self.p.frames)-1,o.which+int(a)))
                return title(o.which,self.p.frames[o.which])
            if cmd not in ('state','titles','out_state'):
                return self.output_action(self.output_editor,cmd,s,a,b)
        if cmd=='recording':return str(int(self.recording))
        if cmd=='sources':return '\n'.join(label(Path(q.path).name) for q in self.p.sources)
        if cmd=='planes':return '\n'.join(label(Path(self.p.sources[i].path).name)+(f' · Z {z+1}' if self.p.sources[i].planes>1 else '') for i,z in self.rows())
        if cmd=='objects':return '\n'.join(('Region' if q.crop or q.region else 'Whole')+' · '+label(Path(self.p.sources[q.src].path).name)+f' · Z {q.plane+1}' for q in self.f.objects)
        if cmd=='name_value':return self.f.name
        if cmd=='distance_value':return '' if self.f.distance_mm is None else str(self.f.distance_mm)
        if cmd=='name':
            self.f.name=label(s).strip();self.dirty=True;return ''
        if cmd=='distance':
            v=float(s.strip()) if s.strip() and s.strip().lower()!='na' else None
            if self.f.distance_mm!=v:self.f.distance_mm=v;self.dirty=True
            return ''
        if cmd=='addframe':
            super().act(cmd,s);self.f.name=s;return ''
        if cmd=='row':self.setrow(int(a));return ''
        if cmd=='regions':return '\n'.join('Region '+r.id[:8] for r in self.regions())
        if cmd=='whole':return super().act('place','',self.z+1)
        if cmd=='region_place':
            regs=self.regions()
            if not 0<=int(a)<len(regs):raise ValueError('Choose a saved crop region.')
            r=regs[int(a)];src=self.p.sources[self.src]
            if len(self.f.objects)>=256:raise ValueError('Maximum 256 placements per frame.')
            l,t,rr,bottom=r.shape(src).bounds;pv=((l+rr)/2,(t+bottom)/2)
            self.f.objects.append(Object(src=self.src,plane=self.z,region=r.id,pivot=pv,x=pv[0],y=pv[1]))
            self.sel=len(self.f.objects)-1;self.dirty=True;return ''
        if cmd=='open':
            self.close_view()
            if s=='source':
                if self.src<0:raise ValueError('Select a slide.')
            elif s!='align':raise ValueError('Unknown editor.')
            self.mode=s;return ''
        if cmd=='close_view':self.close_view();return ''
        if cmd=='viewport':
            if not self.mode or min(a,b)<1:raise ValueError('No open mapping viewport.')
            self.view_for(self.mode,int(a),int(b));return ''
        if cmd=='draft':return str(int(bool(self.draft)))
        if cmd=='autofit':self.camera=None;return ''
        if cmd in ('point','begin','finish','cut','back','clear_draft','region_hit','region_delete'):
            if self.mode!='source' or self.camera is None:raise ValueError('Open a source slide first.')
            if cmd=='point':
                self.last_xy=(a,b)
                if self.recording:self.sample(a,b)
            elif cmd=='begin':
                self.recording=True
                if self.last_xy:self.sample(*self.last_xy)
            elif cmd in ('finish','cut'):self.commit_crop(cmd=='cut')
            elif cmd=='clear_draft':self.draft=[];self.recording=False
            elif cmd=='back':self.recording=False;del self.draft[-10:]
            elif cmd=='region_hit':
                self.region_id=self.hit_region(a,b);self.recording=False;return self.region_id or ''
            elif cmd=='region_delete':
                key=self.region_id
                if not key or not any(r.id==key for r in self.regions()):return ''
                self.f.regions=[r for r in self.f.regions if r.id!=key]
                self.f.objects=[o for o in self.f.objects if o.region!=key];self.region_id=None;self.sel=-1;self.dirty=True
            return ''
        if cmd=='zoom' and self.mode and self.camera:
            x,y=self.world(a,b);k=max(1e-6,min(128.,self.camera[2]*math.pow(1.25,max(-10,min(10,int(s))))));self.camera=(a-k*x,b-k*y,k);return ''
        if cmd=='start' and self.mode and self.camera:
            self.gesture=None;mode='pan';o=None
            if self.mode=='source' and self.recording:self.sample(a,b);return ''
            if self.mode=='align':
                tx,ty,k=self.camera
                pivot=next((i for i in reversed(range(len(self.f.objects))) if math.hypot(tx+k*self.f.objects[i].x-a,ty+k*self.f.objects[i].y-b)<=8),-1)
                self.sel=pivot if pivot>=0 else next((i for i,o in reversed(list(enumerate(self.f.objects))) if geom(o,self.p.sources[o.src],self.f).covers(Point(self.coords_at(o,a,b)))),-1)
                if not self.f.active_opacity and self.frame:self.sel=-1
                if self.sel>=0:
                    o=self.pick();mode='scale' if s=='right' else 'rotate' if pivot>=0 else 'move'
                elif s=='right':return ''
            self.gesture=[mode,a,b,self.camera,o.model_copy() if o else None,None]
            return str(self.sel)
        if cmd=='motion' and self.mode and self.gesture:
            mode,x,y,(tx,ty,k),org,angle=self.gesture;dx=a-x;dy=b-y
            if math.hypot(dx,dy)<2:return ''
            if mode=='pan':self.camera=tx+dx,ty+dy,k;return ''
            o=self.pick()
            if mode=='move':o.x=max(-1e7,min(1e7,org.x+dx/k));o.y=max(-1e7,min(1e7,org.y+dy/k))
            elif mode=='scale':o.scale=max(.01,min(100.,org.scale*math.exp(max(-20,min(20,dx/180)))))
            else:
                direction=math.degrees(math.atan2(b-(ty+k*org.y),a-(tx+k*org.x)))
                if angle is None:self.gesture[-1]=direction;return ''
                o.angle=(org.angle+direction-angle+180)%360-180
            self.dirty=True;return ''
        if cmd=='end':self.gesture=None;return ''
        return super().act(cmd,s,a,b)
    def output_action(self,out,op,s,a,b):
        result=out.act(op,s,a,b)
        if out.dirty:
            self.p.output=out.f;self.dirty=True;out.dirty=False
        return result
    def coords_at(self,o,x,y):
        return (np.linalg.inv(matrix(o,self.p.sources[o.src]))@[*self.world(x,y),1])[:2]

class OutputWorkspace(Workspace):
    """The single virtual source is the entire registered stack. A pose never belongs to one section."""
    def __init__(self,parent,data):
        super().__init__(parent.hospital)
        self.parent=parent;self.which=0;self.src=0
        self.p=NS(frames=[data],sources=[data.source()])
    def act(self,cmd,s='',a=0,b=0):
        if cmd=='whole':
            if len(self.f.objects)>=256:raise ValueError('Maximum 256 output placements.')
            src=self.p.sources[0];self.f.objects.append(Object(src=0,plane=0,x=src.width/2,y=src.height/2))
            self.sel=len(self.f.objects)-1;self.dirty=True;return ''
        if cmd=='remove':
            self.pick();del self.f.objects[self.sel];self.sel=-1;self.dirty=True;return ''
        return super().act(cmd,s,a,b)
    def placements(self,m):
        left,top,_,_=self.f.extent;outer=m@np.array([[1,0,-left],[0,1,-top],[0,0,1.]])
        layer=self.parent.p.frames[self.which]
        for o in layer.objects:
            s=self.parent.p.sources[o.src]
            yield s,o,outer@matrix(o,s),geom(o,s,layer)
    def placement_mask(self,mask,s,z,m):
        occupied=Image.new('L',mask.size)
        for _,_,a,g in self.placements(m):
            piece=Image.new('L',mask.size);mask_draw(piece,g,a,255)
            occupied=ImageChops.lighter(occupied,piece)
        return ImageChops.multiply(mask,occupied)
    def image_for(self,src,z,m,size,clip,detail):
        canvas=Image.new('RGB',size,'white')
        if not clip:return canvas
        for s,o,a,g in self.placements(m):
            mask=Image.new('L',size);mask_draw(mask,g,a,255)
            bbox=mask.getbbox()
            if not bbox:continue
            area=(max(clip[0],bbox[0]),max(clip[1],bbox[1]),min(clip[2],bbox[2]),min(clip[3],bbox[3]))
            if area[0]<area[2] and area[1]<area[3]:
                canvas.paste(self.parent.image_for(s,o.plane,a,size,area,detail),mask=mask)
        return canvas
