"""Real SDK pixel and output-layout regression checks on synthetic scanner data."""
from pathlib import Path
import json
import numpy as np
import tifffile
from PIL import Image
from workspace import Workspace
from project import save,document
from easypath.wsi.transform_source import NativeTransformSource

def detailed(root):
    path=root/'detail.svs'
    y,x=np.indices((768,1536));a=np.stack([(x%2)*229,(y%3)*84,(x+7*y)%256],-1).astype('u1')
    with tifffile.TiffWriter(path) as f:
        f.write(a,photometric='rgb',tile=(128,128),compression='deflate',metadata=None,
                description='Aperio Image Library v12.4.3\n1536x768 (128x128) |AppMag = 40|MPP = 0.25')
        f.write(a[::4,::4],photometric='rgb',metadata=None,description='thumbnail')
    e=Workspace(False);assert e.srgb;e.act('input',str(path));e.act('whole')
    try:
        e.act('open','align');e.camera=(-750,-330,1);e.size=(141,101);e.sel=-1
        sample=np.asarray(e.paint('align',141,101));np.testing.assert_array_equal(sample[:36,:],a[330:366,750:891])
        assert e.pixels.sessions and e.pixels.patches
        o=e.f.objects[0];o.mirror_x=True;o.angle=90
        oriented=np.asarray(e.paint('align',141,101))
        yy,xx=np.indices((26,35));np.testing.assert_array_equal(oriented[:26,:35],a[401-xx,821-yy])
        o.mirror_x=False;o.angle=0;e.act('close_view')
        assert not e.pixels.sessions and not e.pixels.patches
        e.act('out_whole');e.act('out_open','source')
        out=e.output_editor;out.camera=(-750,-330,1);out.size=(141,101)
        np.testing.assert_array_equal(np.asarray(e.paint('source',141,101)),a[330:431,750:891])
    finally:e.close_view()

def output_case(root,scan,stack,inverted,cmd):
    e=Workspace(False);e.act('input',str(scan));e.act('whole');e.act('addframe','Other')
    e.act('input',str(stack));e.act('place','',2)
    e.act('out_open','source');e.act('viewport','',347,223);out=e.output_editor
    out.camera=(0,0,1)
    for action,pts in [('finish',[(8,10),(108,10),(108,90),(8,90)]),('cut',[(26,30),(38,30),(38,44),(26,44)])]:
        out.last_xy=None;e.act('begin')
        for x,y in pts:e.act('point','',x,y)
        e.act(action)
    e.act('close_view');e.act('out_region_place','',0);e.act('out_open','align')
    e.act('viewport','',347,223);out.camera=(0,0,1)
    e.act('start','left',18,20);e.act('motion','',24,28);e.act('end');e.act('flip');e.act('close_view')
    doc=root/'output.epmap';save(e.p,doc);model=document(doc);o=model.output.objects[0]
    assert o.region and o.mirror_x and o.x==64 and o.y==58
    # Two distinct placements set the output extent and test shared registration.
    e.act('out_region_place','',0);second=e.p.output.objects[-1];second.x+=119;second.y+=8
    doc=root/'arranged.epmap';save(e.p,doc);assert document(doc)==e.p
    for ext in ('ep','tiff'):
        dest=root/('layout.'+ext);req=root/(ext+'.req')
        req.write_text(json.dumps(dict(target=str(dest),bits=8,loss=0,distance=4,srgb=True)))
        cmd(['--check-project',doc,req])
        with NativeTransformSource.open(dest,assume_srgb=True) as r:
            assert len(r.stack.rasters)==2
            for f,ref in enumerate([255-inverted,inverted]):
                np.testing.assert_array_equal(r.read(f,0,0,0,13,12),ref[10:22,95:108][:,::-1])
                assert (r.read(f,0,73,23,5,5)==255).all() and (r.read(f,0,103,0,5,12)==255).all()
                np.testing.assert_array_equal(r.read(f,0,113,0,13,12),ref[10:22,8:21])
    e.p.frames[0].objects[0].x-=11
    assert e.act('out_state').startswith('-1 ')
    try:e.act('out_region_place','',0)
    except ValueError:pass
    else:raise AssertionError('Stale crop accepted')
    assert e.p.output.objects;e.act('out_reset');assert not e.p.output.objects
