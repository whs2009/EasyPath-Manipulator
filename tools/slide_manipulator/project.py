"""Local, versioned frame mappings. Coordinates and crops are in native slide pixels."""
import json, math, os, shutil, tempfile
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Annotated, Literal
import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from shapely import Polygon, MultiPolygon, box
from mapping_raster import MappingRaster, pose, transform, selected_plane, plane_key
from easypath.wsi.desktop_converter import output_path, publish, _stamp
from easypath.wsi.transform_source import NativeTransformSource

class Model(BaseModel):
    model_config=ConfigDict(extra='forbid', strict=True, allow_inf_nan=False, validate_assignment=True)
class Source(Model):
    path:str
    width:int=Field(ge=1,le=500000)
    height:int=Field(ge=1,le=500000)
    planes:int=Field(ge=1,le=20)
    size:int=Field(gt=0)
    mtime:int
class Object(Model):
    src:int=Field(ge=0)
    plane:int=Field(ge=0,lt=20)
    x:float=Field(ge=-1e7,le=1e7)
    y:float=Field(ge=-1e7,le=1e7)
    angle:float=Field(default=0,ge=-360,le=360)
    scale:float=Field(default=1,ge=.01,le=100)
    mirror_x:bool=False
    mirror_y:bool=False
    crop:list[tuple[float,float]]=Field(default_factory=list,max_length=4096)
    region:str|None=Field(default=None,max_length=40)
    pivot:tuple[float,float]|None=None
class Region(Model):
    id:str=Field(min_length=1,max_length=40)
    src:int=Field(ge=0)
    plane:int=Field(ge=0,lt=20)
    parts:list[list[list[tuple[float,float]]]]=Field(min_length=1,max_length=128)
    def shape(self,s):
        rings=[r for part in self.parts for r in part]
        if any(not part for part in self.parts) or sum(map(len,rings))>8192 or any(len(r)<4 or r[0]!=r[-1] for r in rings):
            raise ValueError('Invalid crop rings.')
        g=MultiPolygon([Polygon(p[0],p[1:]) for p in self.parts])
        if g.is_empty or not g.is_valid or not box(0,0,s.width,s.height).covers(g):raise ValueError('Invalid saved crop.')
        return g
class Frame(Model):
    name:str=Field(default='',max_length=120)
    distance_mm:float|None=Field(default=None,ge=0)
    regions:list[Region]=Field(default_factory=list,max_length=256)
    objects:list[Object]=Field(default_factory=list,max_length=256)
    base_opacity:Annotated[int,Field(ge=0,le=10)]=3
    active_opacity:Annotated[int,Field(ge=0,le=10)]=5
class Layout(Frame):
    extent:tuple[int,int,int,int]
    def source(self):
        x,y,r,b=self.extent
        if not 0<r-x<=20_000_000 or not 0<b-y<=20_000_000:raise ValueError('Invalid merged slide extent.')
        return NS(width=r-x,height=b-y,path='Merged slide',planes=1)
    def verify(self):
        s=self.source()
        if len({r.id for r in self.regions})!=len(self.regions):raise ValueError('Duplicate output crop.')
        for r in self.regions:
            if r.src or r.plane:raise ValueError('Output crops apply to the whole stack.')
            r.shape(s)
        for o in self.objects:
            if o.src or o.plane:raise ValueError('Output placements apply to the whole stack.')
            if o.crop:raise ValueError('Use a saved output region for cropping.')
            geom(o,s,self)
    def raster(self,extent):
        if self.extent!=tuple(extent):raise ValueError('Merged slide bounds changed. Reset the Output layout before generating.')
        self.verify();s=self.source()
        return NS(extent=extent,regions=[NS(id=r.id,geometry=lambda r=r:r.shape(s)) for r in self.regions],
                  objects=[NS(id=str(i),pivot=o.pivot or (s.width/2,s.height/2),**o.model_dump(include={'x','y','mirror_x','mirror_y','scale','angle','region'})) for i,o in enumerate(self.objects)])
class Project(Model):
    version:Literal[1,2,3]=3
    output:Layout|None=None
    sources:list[Source]=Field(default_factory=list,max_length=128)
    frames:list[Frame]=Field(default_factory=lambda:[Frame()],min_length=1,max_length=20)
    def validate_links(self):
        if not self.frames or len(self.frames)>20 or len(self.sources)>128:raise ValueError('Project limit exceeded.')
        for s in self.sources:
            if not Path(s.path).is_absolute() or Path(s.path).suffix.lower() not in SUFFIXES:raise ValueError('Expected an absolute local slide path.')
        for f in self.frames:
            if len(f.objects)>256:raise ValueError('Too many placements.')
            if len({r.id for r in f.regions})!=len(f.regions):raise ValueError('Duplicate crop ID.')
            for r in f.regions:
                if r.src>=len(self.sources) or r.plane>=self.sources[r.src].planes:raise ValueError('Invalid crop source.')
                r.shape(self.sources[r.src])
            for o in f.objects:
                if o.src>=len(self.sources) or o.plane>=self.sources[o.src].planes:raise ValueError('Missing source or focal plane.')
                geom(o,self.sources[o.src],f)
        if self.output is not None:self.output.verify()
        return self

SUFFIXES={'.svs','.ndpi','.scn','.bif','.mrxs','.svslide','.isyntax','.tif','.tiff','.ep'}
def allowed(p,hospital):
    if p.suffix.lower() not in SUFFIXES or not p.is_file():raise ValueError('Choose a supported local WSI file.')
    if p.suffix.lower()=='.isyntax' and not hospital:raise ValueError('iSyntax requires the Hospital Research edition.')
def probe(p,hospital,srgb):
    p=Path(p).resolve(strict=True);allowed(p,hospital);st=p.stat()
    with NativeTransformSource.open(p,assume_srgb=srgb) as r:
        m=r.metadata.levels[0];n=len(r.stack.rasters) if getattr(r,'stack',None) else 1
    return Source(path=str(p),width=m.width,height=m.height,planes=n,size=st.st_size,mtime=st.st_mtime_ns)
def geom(o,s,frame=None):
    if o.region:
        r=next((r for r in frame.regions if (r.id,r.src,r.plane)==(o.region,o.src,o.plane)),None) if frame else None
        if not r or o.crop:raise ValueError('Missing or ambiguous crop reference.')
        return r.shape(s)
    bounds=box(0,0,s.width,s.height)
    if not o.crop:return bounds
    g=Polygon(o.crop)
    if not g.is_valid or g.area<=0 or not bounds.covers(g):raise ValueError('Draw a non-crossing polygon inside the placement.')
    return g
def obj(o,s,i):
    return NS(id=str(i),region=str(i) if o.crop or o.region else None,source=str(o.src),source_plane=o.plane,
              pivot=o.pivot or (s.width/2,s.height/2),**o.model_dump(include={'angle','scale','mirror_x','mirror_y','x','y'}))
def matrix(o,s):return pose(obj(o,s,0))
def bounds(project):
    footprints=[transform(geom(o,s,f),matrix(o,s)).bounds for f in project.frames for o in f.objects for s in [project.sources[o.src]]]
    if not footprints:raise ValueError('Place a slide in a frame first.')
    a,b,c,d=zip(*footprints)
    return math.floor(min(a)),math.floor(min(b)),math.ceil(max(c)),math.ceil(max(d))
def document(path):
    p=Path(path)
    with p.open('rb') as f:data=f.read(4_194_305)
    if len(data)>4_194_304:raise ValueError('Project file is too large.')
    p=Project.model_validate_json(data).validate_links()
    if p.version==1:
        for i,f in enumerate(p.frames):
            if f.name==('Basal layer' if not i else f'Frame {i}'):f.name=''
            for j,o in enumerate(f.objects):
                if not o.crop:continue
                src=p.sources[o.src];g=geom(o,src);key=f'legacy-{j}'
                f.regions.append(Region(id=key,src=o.src,plane=o.plane,parts=[[list(g.exterior.coords)]]))
                l,t,r,b=g.bounds;pivot=((l+r)/2,(t+b)/2);x,y,_=matrix(o,src)@[*pivot,1]
                o.pivot=pivot;o.x=float(x);o.y=float(y);o.crop=[];o.region=key
    if p.version<3 and p.output is None and any(f.objects for f in p.frames):
        p.output=Layout(extent=bounds(p));s=p.output.source()
        p.output.objects.append(Object(src=0,plane=0,x=s.width/2,y=s.height/2))
    p.version=3
    return p.validate_links()
def save(project,path):
    project.validate_links()
    p=Path(path)
    if p.suffix.lower()!='.epmap':raise ValueError('Use an .epmap project filename.')
    with tempfile.TemporaryDirectory(dir=p.parent) as t:
        tmp=Path(t)/'project';tmp.write_text(project.model_dump_json(indent=2),encoding='utf-8')
        if tmp.stat().st_size>4_194_304:raise ValueError('Project exceeds the supported document size.')
        publish(tmp,p)
def facts_for(project,path):
    from easypath.wsi.transform_dicom import DicomExportInfo
    if not path:raise ValueError('Choose verified DICOM facts first.')
    with Path(path).open('rb') as f:raw=f.read(1_048_577)
    if len(raw)>1_048_576:raise ValueError('DICOM facts file is too large.')
    d=json.loads(raw)
    if set(d)!={'mpp_x','mpp_y','sections'} or not isinstance(d['sections'],list) or len(d['sections'])!=len(project.frames):
        raise ValueError('Provide output mpp_x, mpp_y and one verified section per frame, in order.')
    mpp=(d['mpp_x'],d['mpp_y'])
    if not all(type(v) in (float,int) and math.isfinite(v) and v>0 for v in mpp):raise ValueError('Verify output pixel spacing.')
    facts=[DicomExportInfo.model_validate_json(json.dumps(v,allow_nan=False)) for v in d['sections']]
    distinct=set()
    for f,info in zip(project.frames,facts):
        src={(o.src,o.plane) for o in f.objects}
        if len(src)!=1 or info.associated:raise ValueError('Each DICOM section needs one source and no associated images.')
        p=Path(project.sources[next(iter(src))[0]].path)
        st=p.stat();identity=(st.st_dev,st.st_ino)
        if identity in distinct:raise ValueError('Do not represent focal planes as separate physical specimens.')
        distinct.add(identity)
    if len({i.slide_identifier for i in facts})!=len(facts) or len({(i.patient_identifier,i.patient_name) for i in facts})!=1:
        raise ValueError('Verify distinct slides and matching patient details.')
    return mpp,facts if len(facts)>1 else facts[0]
def generate(project,target,*,hospital=False,srgb=False,bits=8,loss=5,distance=4,facts=None,check=lambda:None):
    project.validate_links();p=Path(target);fmt=p.suffix.lower()[1:]
    dest=output_path(p.parent,p.stem,fmt)
    if os.path.lexists(dest):raise FileExistsError('Destination exists; choose a new name.')
    if any(not f.objects for f in project.frames):raise ValueError('Place at least one slide in every frame.')
    if not (5<=bits<=8 and 0<=loss<=15 and 1<=distance<=15):raise ValueError('Invalid EP settings.')
    extent=bounds(project)
    mpp,info=facts_for(project,facts) if fmt=='dcm' else ((None,None),None)
    with ExitStack() as opened:
        sources={};stamps={}
        for i in sorted({o.src for f in project.frames for o in f.objects}):
            s=project.sources[i];path=Path(s.path);allowed(path,hospital);check()
            if path.suffix.lower()=='.mrxs' and dest.parent.is_relative_to(path.with_suffix('')):raise ValueError('Destination is inside a source package.')
            st=path.stat()
            if (st.st_size,st.st_mtime_ns)!=(s.size,s.mtime):raise ValueError('Source changed. Import it again.')
            stamps[path]=_stamp(path,check)
            r=opened.enter_context(NativeTransformSource.open(path,assume_srgb=srgb,check_cancel=check))
            for z in {o.plane for f in project.frames for o in f.objects if o.src==i}:
                sel=selected_plane(r,z);level=sel.metadata.levels[0]
                if (level.width,level.height)!=(s.width,s.height):raise ValueError('Focal plane dimensions changed.')
                sources[plane_key(str(i),z)]=sel
        frames=[]
        for f in project.frames:
            objs=[];regs=[]
            for i,o in enumerate(f.objects):
                s=project.sources[o.src];objs.append(obj(o,s,i))
                if o.crop or o.region:regs.append(NS(id=str(i),geometry=lambda g=geom(o,s,f):g))
            frames.append(NS(objects=objs,regions=regs))
        identity=NS(id='output',pivot=(0,0),x=0,y=0,angle=0,scale=1,mirror_x=False,mirror_y=False,region=None)
        output=project.output.raster(extent) if project.output is not None else NS(extent=extent,regions=[],objects=[identity])
        raster=MappingRaster(frames[0],NS(frames=frames[1:],output=output),sources,mpp=mpp,check=check)
        budget=raster.reservation(fmt);free=shutil.disk_usage(dest.parent).free-(64<<20)
        if fmt=='ep':
            cap=min(budget['output_bytes'],free//(3 if raster.stack else 2))
            budget=dict(budget,output_bytes=cap,reference_bytes=min(budget['reference_bytes'],free-cap))
        else:cap=free-budget['reference_bytes'];budget=dict(budget,output_bytes=min(cap,budget['output_bytes']))
        if cap<=0:raise ValueError('Insufficient space for the mapped slide.')
        with tempfile.TemporaryDirectory(prefix='.ep-mapping-',dir=dest.parent) as t:
            work=Path(t);report=raster.write(work,NS(format=fmt,bits=bits,loss=loss,distance=distance),dicom=info,budget=budget)
            if report.get('verified') is not True:raise ValueError('Output failed verification.')
            artifact=work/('slide.'+fmt+'.partial')
            files={artifact:report['sha256']} if fmt!='dcm' else {artifact/n:v['sha256'] for n,v in report['files'].items()}
            if fmt=='dcm' and set(files)!={child for child in artifact.rglob('*') if child.is_file()}:raise ValueError('DICOM set changed.')
            import hashlib
            for file,digest in files.items():
                h=hashlib.sha256()
                with file.open('rb') as stream:
                    while block:=stream.read(4<<20):check();h.update(block)
                if h.hexdigest()!=digest:raise ValueError('Output changed after verification.')
            for path,stamp in stamps.items():
                if stamp!=_stamp(path,check):raise ValueError('Source changed during export.')
            check();publish(artifact,dest)
    return dest
