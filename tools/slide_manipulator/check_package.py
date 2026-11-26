import json,os,shutil,sys,subprocess,tempfile
from pathlib import Path
here=Path(__file__).resolve().parent
sys.path[:0]=[str(here),os.environ['EP_READER_SOURCE']]
from accept import fixture
from project import Project,Frame,Object,probe,generate,save,document
from easypath.wsi.transform_source import NativeTransformSource
import numpy as np
def run(exe=None):
    def refused(fn):
        try:fn()
        except (ValueError,OSError,RuntimeError):return
        raise AssertionError('Invalid operation accepted')
    with tempfile.TemporaryDirectory() as t:
        root=Path(t);scan,stack,inverted=fixture(root);reference=255-inverted
        from workspace import Workspace
        ed=Workspace(False);ed.act('srgb','',1);ed.act('input',str(scan));ed.act('place','',1);ed.act('addframe','Other plane');ed.act('input',str(stack));ed.act('place','',2)
        low,high=ed.paint('preview',685,476).getextrema()[0];assert low<high
        ed.act('flip');ed.f.objects[0].x+=4
        ed.f.objects[0].crop=[(2.,0.),(347.,0.),(347.,223.),(2.,223.)]
        project=ed.p;doc=root/'project.epmap';save(project,doc);assert project==document(doc)
        refused(lambda:save(project,doc))
        facts=dict(acquisition_datetime='2025-01-01T10:00:00+00:00',focus_method='AUTO',source_was_lossy=False,contains_patient_text=False,imaged_depth_um=1,origin_x_mm=0,origin_y_mm=0,rotation_degrees=0,specimen_identifier='Test',slide_identifier='Test1')
        facts_file=root/'facts.json';facts_file.write_text(json.dumps(dict(mpp_x=.25,mpp_y=.5,sections=[facts,dict(facts,slide_identifier='Test2')])))
        refused(lambda:generate(project,root/'missing.dcm',srgb=True))
        assert not (root/'missing.dcm').exists()
        env={k:v for k,v in os.environ.items() if not k.startswith(('PYTHON','EASYPATH_','EP_READER'))}
        env['APPIMAGE_EXTRACT_AND_RUN']='1'
        def cmd(args,ok=True):
            res=subprocess.run([str(exe),*map(str,args)],cwd=root,env=env,capture_output=True,timeout=200)
            assert (res.returncode==0)==ok,(args[0],res.returncode,res.stderr[-2000:])
        if exe:
            cmd(['--gui-smoke'])
            from check_output_layout import detailed,output_case
            detailed(root);cmd(['--check-detail',root/'detail.svs']);output_case(root,scan,stack,inverted,cmd)
            result=root/'gesture.epmap';cmd(['--check-mapping',scan,result])
            verified=document(result);basal,active,empty=verified.frames
            assert verified.output and len(verified.output.objects)==2 and len(verified.output.regions)==1
            assert not empty.objects and len(basal.objects)==len(active.objects)==len(active.regions)==1
            assert not basal.regions and basal.objects[0].angle==0 and basal.objects[0].scale==1
            assert active.name=='IHC' and active.distance_mm==.25 and (active.base_opacity,active.active_opacity)==(4,7)
            placed=active.objects[0]
            assert placed.region==active.regions[0].id and placed.mirror_x and placed.mirror_y
            assert 85<placed.angle<96 and 1.18<placed.scale<1.21 and all(a>b for a,b in zip((placed.x,placed.y),placed.pivot))
            assert result.is_file() and scan.is_file()
            # Exercise a saved local crop with an interior hole through the installed writer.
            e=Workspace(False);e.act('srgb','',1);e.act('input',str(scan));e.act('whole');e.act('addframe')
            e.mode='source';e.camera=(0,0,1)
            for c,pts in [('finish',[(2,2),(100,2),(100,90),(2,90)]),('cut',[(20,20),(40,20),(40,40),(20,40)])]:
                e.last_xy=None;e.act('begin')
                for x,y in pts:e.act('point','',x,y)
                e.act(c)
            e.act('region_place','',0);hole_doc=root/'hole.epmap';save(e.p,hole_doc)
            hole_out=root/'hole.ep';hole_req=root/'hole.json'
            hole_req.write_text(json.dumps(dict(target=str(hole_out),bits=8,loss=0,distance=4,srgb=True)))
            cmd(['--check-project',hole_doc,hole_req])
            with NativeTransformSource.open(hole_out,assume_srgb=True) as r:
                np.testing.assert_array_equal(r.read(0,0,24,24,8,8),reference[24:32,24:32])
                np.testing.assert_array_equal(r.read(1,0,8,8,8,8),reference[8:16,8:16])
                assert (r.read(1,0,24,24,8,8)==255).all()
        for fmt in ('ep','tiff','dcm'):
            dest=root/('mapped.'+fmt)
            req=dict(target=str(dest),srgb=True,bits=8,loss=0,distance=4,facts=str(facts_file) if fmt=='dcm' else None)
            if exe:
                r=root/'request.json';r.write_text(json.dumps(req));cmd(['--check-project',doc,r]);cmd(['--check-project',doc,r],False)
            else:generate(project,**req)
            if fmt in ('ep','tiff'):
                with NativeTransformSource.open(dest,assume_srgb=True) as read:
                    assert len(read.stack.rasters)==2
                    np.testing.assert_array_equal(read.read(0,0,0,0,55,45),reference[:45,:55])
                    np.testing.assert_array_equal(read.read(1,0,4,0,55,45),inverted[:45,::-1][:,:55])
                    assert (read.read(1,0,0,0,4,30)==255).all()
            else:
                from wsidicom import WsiDicom
                for i,want in enumerate([reference[:25,:25],inverted[:25,::-1][:,:25]]):
                    with WsiDicom.open(dest/f'section-{i:02d}') as reader:
                        actual=np.asarray(reader.read_region((4 if i else 0,0),0,(25,25)).convert('RGB'));np.testing.assert_array_equal(actual,want)
        print('Passed native project geometry, two planes, clipping, flip, pixel checks, verified DICOM sections and overwrite refusal.',flush=True)
if __name__=='__main__':run(Path(sys.argv[1]).resolve(strict=True) if len(sys.argv)>1 else None)
