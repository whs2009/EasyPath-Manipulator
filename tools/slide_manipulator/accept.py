import numpy as np
import tifffile

def fixture(folder):
    from easypath.wsi.desktop_converter import convert
    y,x=np.indices((223,347))
    ref=np.stack([x%256,y%256,(x+y)%256],axis=-1).astype("u1")
    scan=folder/"synthetic.svs"
    with tifffile.TiffWriter(scan) as tw:
        options=dict(photometric="rgb",metadata=None,compression="deflate")
        tw.write(ref,description="Aperio Image Library v12.4.3\n347x223 (128x128) |AppMag = 40|MPP = 0.25",tile=(128,128),**options)
        tw.write(ref[::4,::4],description="thumbnail",**options)
        label=np.zeros((40,32,3),"u1");label[:,2::4]=255;label[:,3::4]=255
        tw.write(label,description="Aperio Image Library\nlabel 32x40",subfiletype=1,**options)
        glass=np.full((40,100,3),(18,180,55),"u1")
        tw.write(glass,description="Aperio Image Library\nmacro 100x40",extratags=[(254,"I",1,9,False)],**options)
    source=folder/"synthetic.ome.tif"
    tifffile.imwrite(source,np.stack([ref,255-ref,np.roll(ref,17,axis=0)]),ome=True,
        metadata={"axes":"ZYXS","PhysicalSizeX":.25,"PhysicalSizeY":.5,"PhysicalSizeXUnit":"\u00b5m","PhysicalSizeYUnit":"\u00b5m",
                  "Plane":{"PositionZ":[-1.,0.,1.],"PositionZUnit":["\u00b5m"]*3}},tile=(128,128),photometric="rgb",compression="deflate")
    convert(source,folder,"stack","ep",loss=0,assume_srgb=True)
    return scan,folder/"stack.ep",255-ref

