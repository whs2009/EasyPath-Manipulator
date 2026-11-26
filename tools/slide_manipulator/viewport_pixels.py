"""Render a transformed SDK viewport without reading a full slide or full-resolution layer."""
from collections import OrderedDict
import math
import numpy as np
from PIL import Image
from engine import Session

class ViewportPixels:
    def __init__(self,hospital):
        self.hospital=hospital;self.sessions=OrderedDict();self.patches=OrderedDict();self.bytes=0
    def close(self):
        for session in self.sessions.values():session.close()
        self.sessions.clear();self.patches.clear();self.bytes=0
    def session(self,s):
        key=(s.path,s.size,s.mtime)
        if key not in self.sessions:
            if len(self.sessions)>=4:self.sessions.popitem(last=False)[1].close()
            reader=Session(self.hospital)
            try:reader.open(s.path)
            except BaseException:reader.close();raise
            self.sessions[key]=reader
        self.sessions.move_to_end(key);return self.sessions[key]
    def patch(self,s,reader,plane,x,y,zoom,w,h):
        key=(s.path,s.size,s.mtime,plane,x,y,zoom,w,h)
        if key not in self.patches:
            im=Image.fromarray(reader.render(x,y,zoom,w,h,plane))
            self.patches[key]=im;self.bytes+=w*h*3
            while self.bytes>24*1024**2:
                _,old=self.patches.popitem(last=False);self.bytes-=old.width*old.height*3
        self.patches.move_to_end(key);return self.patches[key]
    def image(self,s,plane,thumb,m,size,clip,detail):
        inv=np.linalg.inv(m);k=math.hypot(m[0,0],m[1,0]);w,h=size
        overview=np.diag([thumb.width/s.width,thumb.height/s.height,1.])@inv
        im=thumb.transform(size,Image.Transform.AFFINE,overview[:2].ravel(),Image.Resampling.BILINEAR)
        if not detail or not clip or k<=1.05*min(thumb.width/s.width,thumb.height/s.height):return im
        reader=self.session(s);factor=reader.dims[5]
        zoom=max(-12,min(16,round(12+math.log2(min(k,1)*factor))))
        step=2.**(12-zoom);pitch=step*factor
        l,t,r,b=clip
        for top in range(t,b,384):
            for left in range(l,r,384):
                right=min(r,left+384);bottom=min(b,top+384)
                corners=inv@np.array([[left,right,left,right],[top,top,bottom,bottom],[1,1,1,1]])
                x0,y0=np.maximum(0,corners[:2].min(axis=1)-pitch*2)
                x1,y1=np.minimum([s.width,s.height],corners[:2].max(axis=1)+pitch*2)
                if x1<=x0 or y1<=y0:continue
                sx=math.floor(x0/factor);sy=math.floor(y0/factor)
                pw=math.ceil((x1/factor-sx)/step);ph=math.ceil((y1/factor-sy)/step)
                if pw*ph>4_194_304 or max(pw,ph)>4096:raise ValueError('SDK viewport exceeds the read budget.')
                patch=self.patch(s,reader,plane,sx,sy,zoom,pw,ph)
                tile_inv=inv.copy();tile_inv[:2,2]+=(inv[:2,:2]@[left,top])-np.array([sx,sy])*factor
                tile_inv[:2]/=pitch
                # A quarter turn should permute pixels without interpolating a near-integer.
                exact=np.rint(tile_inv)
                if np.allclose(tile_inv,exact,rtol=0,atol=1e-10):tile_inv=exact
                out=patch.transform((right-left,bottom-top),Image.Transform.AFFINE,tile_inv[:2].ravel(),Image.Resampling.BILINEAR)
                im.paste(out,(left,top))
        return im
