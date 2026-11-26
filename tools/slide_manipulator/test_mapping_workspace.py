import json,tempfile,unittest
from pathlib import Path
import numpy as np
from PIL import Image
from project import Source,Frame,Object,Project,document,save,geom,matrix
from workspace import Workspace,title

class MappingWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.path=Path(self.t.name)/'synthetic.svs';self.path.write_bytes(b'identity')
        self.src=Source(path=str(self.path),mtime=1,size=8,width=100,height=80,planes=2)
        self.e=Workspace(False);self.e.p.sources=[self.src];self.e.src=0
        self.e.thumb=lambda *args: Image.new('RGB',(100,80),'#906030')
        self.e.mode='source';self.e.camera=(0,0,1);self.e.size=(100,80)
    def draw(self,pts,cut=False):
        self.e.last_xy=None;self.e.act('begin')
        for x,y in pts:self.e.act('point','',x,y)
        self.e.act('cut' if cut else 'finish')
    def test_overlapping_crops_preserve_registered_pixels(self):
        e=self.e;self.draw([(2,2),(18,2),(18,16),(2,16)]);e.act('region_place','',0)
        o=e.f.objects[0];o.angle=37;o.scale=.8;o.mirror_y=True;o.x=43;before=matrix(o,self.src)
        self.draw([(12,9),(30,9),(30,24),(12,24)])
        self.assertEqual((len(e.f.regions),len(e.f.objects)),(1,1))
        np.testing.assert_allclose(before,matrix(e.f.objects[0],self.src),atol=1e-12)
    def test_cut_hole_keeps_exterior_and_roundtrips(self):
        e=self.e;self.draw([(1,1),(60,1),(60,60),(1,60)]);e.act('region_place','',0)
        self.draw([(10,10),(18,10),(18,18),(10,18)],True)
        path=Path(self.t.name)/'hole.epmap';save(e.p,path);f=document(path).frames[0]
        self.assertEqual(geom(f.objects[0],self.src,f).area,59*59-64)
        self.assertEqual(len(f.regions[0].parts[0]),2)
    def test_delete_only_selected_region_in_selected_plane_and_frame(self):
        e=self.e
        for z in [0,1]:
            e.z=z;self.draw([(1,1),(15,1),(15,15),(1,15)]);e.act('region_place','',0)
        e.p.frames.append(e.f.model_copy(deep=True));before=e.p.frames[1].model_dump()
        e.z=0;self.assertTrue(e.act('region_hit','',5,5));e.act('region_delete')
        self.assertEqual([o.plane for o in e.f.objects],[1])
        self.assertEqual(e.p.frames[1].model_dump(),before)
    def test_invalid_draft_cannot_replace_existing_crop(self):
        self.draw([(1,1),(16,1),(16,16)]);before=self.e.f.model_dump()
        with self.assertRaises(ValueError):self.draw([(4,4),(8,8),(14,14)])
        self.assertEqual(before,self.e.f.model_dump());self.assertTrue(self.e.draft)
        self.e.act('clear_draft');self.assertFalse(self.e.draft)
    def test_readonly_preview_does_not_share_camera(self):
        e=self.e;e.f.objects=[Object(src=0,plane=0,x=50.,y=40.)];e.mode='align'
        e.p.frames.append(Frame());e.act('frame','',1);self.assertEqual(e.act('start','left',50,40),'-1')
        e.act('motion','',62,46);e.act('end')
        camera=e.camera;old=e.p.model_dump();e.paint('preview',350,190)
        self.assertEqual(e.camera,camera);self.assertEqual(old,e.p.model_dump());self.assertEqual(e.p.frames[0].objects[0].x,50)
    def test_first_input_before_expose_and_resize(self):
        e=self.e;e.act('whole');e.act('open','align');self.assertIsNone(e.camera)
        for w,h in ((260,160),(400,260)):
            e.act('viewport','',w,h);self.assertEqual(e.size,(w,h))
            self.assertEqual(e.act('start','left',w/2,h/2),'0');e.act('end')
        old=e.camera;e.act('zoom','1',100,90);e.act('viewport','',400,260)
        self.assertNotEqual(old,e.camera)
    def test_load_version_one_crop_keeps_alignment(self):
        e=self.e;o=Object(src=0,plane=0,x=11.,y=16.,angle=29.,mirror_x=True,scale=.7,crop=[(1.,1.),(25.,1.),(12.,9.)])
        original=matrix(o,self.src);f=Path(self.t.name)/'v1.epmap'
        v1=dict(version=1,sources=[self.src.model_dump()],frames=[dict(name='Basal layer',objects=[o.model_dump(exclude={'region','pivot'})])])
        f.write_text(json.dumps(v1));p=document(f);self.assertEqual(p.version,3)
        self.assertEqual(title(0,p.frames[0]),'Basal layer');self.assertTrue(p.frames[0].objects[0].region)
        np.testing.assert_allclose(original,matrix(p.frames[0].objects[0],self.src),atol=1e-12)
    def test_frame_insertion_reorder_and_distance_validation(self):
        e=self.e;e.act('addframe','A');e.act('addframe','B');e.act('frame','',1);e.act('addframe','C')
        self.assertEqual([f.name for f in e.p.frames],['','A','C','B'])
        e.act('distance','1.25');e.act('order','',1);self.assertEqual(e.f.name,'C');self.assertEqual(e.f.distance_mm,1.25)
        with self.assertRaises(ValueError):e.act('distance','nan')
        e.act('frame','',0)
        with self.assertRaises(ValueError):e.act('order','',1)
        with self.assertRaises(ValueError):e.act('deleteframe')
        e.dirty=False;e.act('distance','NA');self.assertFalse(e.dirty)
if __name__=='__main__':unittest.main()
