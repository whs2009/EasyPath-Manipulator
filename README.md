# EasyPath Manipulator

EasyPath Manipulator is a desktop tool for manually aligning serial whole-slide sections. Place an H&E section on the basal layer, align an IHC or GMS section in a second frame, and export both at the same coordinates. You can also bring PAS and PAS-D sections together, or lay several matched tissue fragments side by side. The originals remain unchanged. No EasyPath Server or Python installation is required to run a packaged download.

## Download the General edition

Download the **0.3.1 General edition** for your platform below. Compare the SHA-256 of your download with [SHA256SUMS](https://github.com/whs2009/EasyPath-Manipulator/releases/download/v0.3.1-general.1/SHA256SUMS). See [Releases](https://github.com/whs2009/EasyPath-Manipulator/releases) for other versions.

| Platform | Release asset |
| --- | --- |
| Windows x86-64 | [EasyPath-Slide-Manipulator-windows-x64.exe](https://github.com/whs2009/EasyPath-Manipulator/releases/download/v0.3.1-general.1/EasyPath-Slide-Manipulator-windows-x64.exe) |
| macOS Apple silicon | [EasyPath-Slide-Manipulator-macos-arm64.dmg](https://github.com/whs2009/EasyPath-Manipulator/releases/download/v0.3.1-general.1/EasyPath-Slide-Manipulator-macos-arm64.dmg) |
| macOS Intel | [EasyPath-Slide-Manipulator-macos-x64.dmg](https://github.com/whs2009/EasyPath-Manipulator/releases/download/v0.3.1-general.1/EasyPath-Slide-Manipulator-macos-x64.dmg) |
| Ubuntu x86-64 | [EasyPath-Slide-Manipulator-ubuntu-x64.AppImage](https://github.com/whs2009/EasyPath-Manipulator/releases/download/v0.3.1-general.1/EasyPath-Slide-Manipulator-ubuntu-x64.AppImage) |
| Ubuntu ARM64 | [EasyPath-Slide-Manipulator-ubuntu-arm64.AppImage](https://github.com/whs2009/EasyPath-Manipulator/releases/download/v0.3.1-general.1/EasyPath-Slide-Manipulator-ubuntu-arm64.AppImage) |

Open the executable on Windows, make the AppImage executable on Ubuntu, or open the DMG and copy the app to Applications on macOS. Follow your institution's software installation policy.

## Worked example: align H&E with IHC

1. In **Input**, select both slides. Keep companion files beside the originals, for example the data folder of an MRXS slide. For a supported stack, choose the source plane in the layer tab.
2. Name the **Basal layer** H&E. Choose **Add whole slide**, or **Open** the source and trace a fragment with **Shift+Z**. **Shift+S** saves the crop; **Add segmented region** places it. These polygons are mapping masks, not annotations.
3. Choose **Add frame**, name it IHC, and place the corresponding section. Open **Open manipulation**. Start with the basal overlay at 0.3 and the active frame at 0.5. Drag a shared tissue landmark into position, rotate using the center dot, and check a second landmark away from the first. Right-drag horizontally to scale; double-click a placement to flip horizontally or vertically. Mirror only when the section orientation warrants it.
4. Inspect the same landmarks at higher zoom. The tab preview is read-only; editing happens in the opened manipulation window. The opacity sliders help with alignment and do not blend stains into the exported planes. Adjacent tissue sections need not have the same structures at every location. The tool does not perform deformable registration or establish cell-to-cell correspondence.
5. Repeat with further frames as needed. For H&E/GMS, place GMS in its own frame. For PAS/PAS-D, use PAS as basal and PAS-D as the corresponding frame. Frame order determines output plane order; optional frame distances are project metadata, not verified acquisition spacing.
6. In **Output** there is one **Merged slide**, not a list of independent layers. Open it to inspect the frames and draw a region that covers the tissue of interest. Add the whole merged slide or one or more crops and arrange them. Moving a crop in Output moves all its frames together. Uncovered areas are white. If the underlying bounds change, reset the output layout and select the crops again.
7. **Save project** keeps paths, crops, frame order and placements in an `.epmap` file. It does not embed the pixels. **Generate slide** writes a new output. Reopen it and compare the same landmark across frames before sharing the result.

## Output and input support

| Output | When to choose it |
| --- | --- |
| EasyPath `.ep` | Multi-frame WSI with selectable precision and compression. Defaults: 8 bits/channel, maximum 5% error, JPEG XL distance 4. Use 8 bits and 0% for lossless encoding of the rendered pixels. |
| Pyramidal `.tiff` | Losslessly encoded frames in display order. Suitable for registered crops and montages. |
| DICOM WSI `.dcm` directory | Separate physical-section WSI instances. Supply verified output pixel spacing and each section's acquisition and specimen details. Do not substitute a guessed focal position for a differently stained section. See the [user guide](tools/slide_manipulator/USER-GUIDE.md) for restrictions. |

General reads supported SVS, NDPI, MRXS, BIF, SCN, EP and supported pyramidal/focal TIFF files. Scanner support depends on the specific file and reader. Recognized NDPI can open through OpenSlide; **Philips PixelEngine and Hamamatsu NDP.read are not included**. Native iSyntax input is not provided by General. Recipients with appropriate vendor authorization may contact the **EasyPath core team** through their institutional channel about the separate Hospital Research edition for Windows or Ubuntu x86-64. No Hospital binaries are distributed in this repository.

**Annotations:** Standalone Manipulator maps slide pixels only. It neither edits original annotation sidecars nor transfers them to the output. Use **Manipulate mapping in EasyPath Server** for frame-specific annotation routing, copying, merging, clipping or replacing annotations.

## Build and verify

The [General workflow](.github/workflows/general.yml) builds the C++17/FLTK UI natively on each target. Run `python packaging/prepare.py` to materialize the pinned public [Viewer](https://github.com/whs2009/EasyPath-Viewer) reader and [Converter](https://github.com/whs2009/EasyPath-Converter) writer; install the pinned build requirements in an isolated Python 3.12 environment, then run `python packaging/build.py` (use Xvfb on headless Ubuntu). Tests use synthetic slides, reopen generated files, compare pixels across frames, and check that existing outputs cannot be overwritten.

EasyPath-authored public code is licensed under [Apache-2.0](LICENSE). Third-party libraries retain their own licenses and notices. This license does not apply to the private server or proprietary scanner SDKs.
