"""Read one tile of a composed mapping. Output poses are shared by every frame."""
from functools import partial
from types import SimpleNamespace
from math import cos, sin, radians, ceil, floor
from pathlib import Path
import numpy as np
from shapely import affinity, box, intersects_xy
from easypath.wsi.ep_format import EPMetadata, pyramid_levels
from easypath.wsi.focal_stack import FocusStack
from easypath.wsi.transform_contract import conversion_reservation


def pose(o):
    a=radians(o.angle);c,s=cos(a)*o.scale,sin(a)*o.scale
    k=-1 if o.mirror_x else 1
    l=-1 if o.mirror_y else 1
    x,y=o.pivot
    return np.array([[c*k,-s*l,o.x-c*k*x+s*l*y],[s*k,c*l,o.y-s*k*x-c*l*y],[0.,0.,1.]])

def transform(shape,m):
    return affinity.affine_transform(shape,(*m[0,:2],*m[1,:2],m[0,2],m[1,2]))

def shapes(layer):
    return {r.id:r.geometry() for r in layer.regions}


def plane_key(source, index):
    return (source, index) if index else source


def selected_plane(reader, index):
    stack=getattr(reader,"stack",None)
    if stack is None:
        if index:raise ValueError("Selected plane is not present in this slide.")
        return reader
    order=getattr(reader,"viewer_order",range(len(stack.rasters)))
    if not 0<=index<len(order):raise ValueError("Selected plane is not present in this slide.")
    z=order[index]
    return SimpleNamespace(metadata=stack.rasters[z],read_plane=partial(reader.read,z))

class MappingRaster:
    def __init__(self,basal,stack,sources,*,mpp=(None,None),check=lambda:None):
        out=stack.output
        if not out or not out.objects or not out.extent: raise ValueError("Place at least one output object.")
        self.check=check;self.sources=sources;self.layers=[[] for _ in range(1+len(stack.frames))]
        x,y,r,b=out.extent;full=box(0,0,r-x,b-y)
        offset=np.eye(3);offset[0,2]=-x;offset[1,2]=-y
        crops=shapes(out);bounds=[]
        prepared=[]
        for f in (basal,*stack.frames):
            masks=shapes(f);items=[]
            for obj in f.objects:
                source=plane_key(obj.source,obj.source_plane)
                reader=sources[source];g=reader.metadata.levels[0]
                local=box(0,0,g.width,g.height)
                if obj.region: local=local.intersection(masks[obj.region])
                if local.is_empty: continue
                m=offset@pose(obj);foot=transform(local,m)
                if not full.buffer(.00001).covers(foot): raise ValueError("Source dimensions or frame bounds changed. Reopen Output.")
                items.append((source,m,foot))
            prepared.append(items)
        for o in out.objects:
            crop=full.intersection(crops[o.region]) if o.region else full
            if crop.is_empty: raise ValueError("An output crop is outside the merged slide.")
            outer=pose(o);bounds.append(transform(crop,outer).bounds)
            for layer,items in zip(self.layers,prepared,strict=True):
                for source,inner,foot in items:
                    clip=crop.intersection(foot)
                    if not clip.is_empty and clip.area:
                        layer.append((source,np.linalg.inv(outer@inner),transform(clip,outer),o.id))
        left=floor(min(q[0] for q in bounds));top=floor(min(q[1] for q in bounds))
        width=ceil(max(q[2] for q in bounds))-left;height=ceil(max(q[3] for q in bounds))-top
        self.origin=(left,top)
        self.metadata=EPMetadata(source_color_policy="declared-srgb",levels=pyramid_levels(width,height),
                                  mpp_x=mpp[0],mpp_y=mpp[1])
        # Sections are ordered by the user; unknown physical Z is not replaced with a made-up interval.
        self.stack=FocusStack((self.metadata,)*len(self.layers),(None,)*len(self.layers)) if len(self.layers)>1 else None

    def read(self,z,plane,x,y,w,h):
        self.check()
        if plane!=0 or min(w,h)<=0 or max(w,h)>512:raise ValueError("Expected a bounded level-zero tile.")
        column=np.arange(w,dtype=float)[None,:]+x+self.origin[0]+.5
        row=np.arange(h,dtype=float)[:,None]+y+self.origin[1]+.5
        result=np.full((h,w,3),255,dtype=np.uint8)
        for source,inv,foot,_ in self.layers[z]:
            l,t,r,b=foot.bounds
            if l>column[0,-1] or r<column[0,0] or t>row[-1,0] or b<row[0,0]:continue
            iy,ix=np.nonzero(intersects_xy(foot,column,row))
            if not len(ix):continue
            reader=self.sources[source];g=reader.metadata.levels[0]
            pts=inv@np.vstack((column[0,ix],row[iy,0],np.ones(len(ix))))
            sx,sy=np.floor(pts[:2]).astype(np.int64)
            valid=(sx>=0)&(sx<g.width)&(sy>=0)&(sy<g.height)
            sx,sy,ix,iy=(v[valid] for v in (sx,sy,ix,iy))
            if not sx.size:continue
            ids=(sy//512)*((g.width+511)//512)+sx//512
            order=np.argsort(ids,kind="stable");sorted_ids=ids[order]
            for selection in np.split(order,np.flatnonzero(np.diff(sorted_ids))+1):
                px=sx[selection];py=sy[selection];cx=int(px.min());cy=int(py.min())
                data=reader.read_plane(0,cx,cy,int(px.max()-cx+1),int(py.max()-cy+1))
                result[iy[selection],ix[selection]]=data[py-cy,px-cx]
        return result

    def reservation(self,fmt):
        if fmt=="dcm" and self.stack:
            from easypath.wsi.ep_format import MAX_FILE_BYTES
            one=conversion_reservation(self.metadata,fmt)
            budget={k:v*len(self.layers)+4096 for k,v in one.items()}
            if budget["total_bytes"]>MAX_FILE_BYTES:raise ValueError("Section package exceeds its storage limit.")
            return budget
        return conversion_reservation(self.metadata,fmt,self.stack)

    def write(self,work,settings,*,dicom=None,budget=None):
        from easypath.wsi.transform_focus import write_focus_work
        from easypath.wsi.transform_tiff import write_tiff_artifact
        from easypath.wsi.transform_dicom import write_dicom_artifact
        from easypath.wsi.transform_pyramid import RGBPyramid
        from easypath.wsi.ep_stream_writer import write_ep_streaming_artifact
        fmt=settings.format;meta=self.metadata
        budget=budget or self.reservation(fmt)
        dest=Path(work)/("slide."+fmt+".partial");limit=budget["output_bytes"]
        if fmt=="dcm" and self.stack:
            MARKER, SIGNATURE = "easypath-sections.v1", b"EasyPath mapped physical sections v1\n"
            from easypath.wsi.transform_integrity import artifact_snapshot
            if not isinstance(dicom,list) or len(dicom)!=len(self.layers):raise ValueError("Missing per-section DICOM facts.")
            dest.mkdir();files={};one=conversion_reservation(meta,fmt)
            for z,facts in enumerate(dicom):
                name=f"section-{z:02d}"
                with RGBPyramid.build(Path(work)/("reference-"+name),meta,partial(self.read,z),
                        max_workspace_bytes=one["reference_bytes"],check_cancel=self.check) as pyr:
                    tmp=dest/(name+".partial")
                    part=write_dicom_artifact(tmp,pyr,facts,max_file_bytes=one["output_bytes"],check_cancel=self.check)
                if part.get("verified") is not True:raise ValueError("DICOM section did not verify.")
                tmp.rename(dest/name)
                files.update({name+"/"+k:v for k,v in part["files"].items()})
            (dest/MARKER).write_bytes(SIGNATURE)
            files[MARKER]=artifact_snapshot(dest/MARKER,self.check)
            return {"verified":True,"files":files}
        if self.stack:
            return write_focus_work(self,Path(work),fmt,max_file_bytes=limit,bits=settings.bits,loss=settings.loss,
                  distance=settings.distance,dicom=dicom,thickness_um=None,check_cancel=self.check)
        read=partial(self.read,0)
        args={"max_file_bytes":limit,"check_cancel":self.check}
        if fmt=="ep":
            updates={"storage_encoding":"jxl-solid-rgb-v2"}
            if settings.bits<8:updates.update(profile="rgb-jxl-precision-v1",channel_bits=settings.bits,maximum_nrmse_percent=settings.loss)
            elif settings.loss:updates.update(profile="rgb8-jxl-bounded-lossy-v1",maximum_nrmse_percent=settings.loss)
            return write_ep_streaming_artifact(dest,EPMetadata.model_validate(meta.model_dump()|updates),read,
                       max_workspace_bytes=budget["reference_bytes"],jxl_distance=settings.distance,**args)
        with RGBPyramid.build(Path(work)/"reference",meta,read,max_workspace_bytes=budget["reference_bytes"],check_cancel=self.check) as pyr:
            if fmt=="tiff":return write_tiff_artifact(dest,pyr,**args)
            if dicom is None:raise ValueError("Verified DICOM facts required.")
            return write_dicom_artifact(dest,pyr,dicom,**args)
