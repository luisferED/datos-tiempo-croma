"""Same JPEG quality, quantization and chroma sampling; optional Qt fallback."""
import io
import sys
from PIL import Image
from PyQt6.QtCore import QByteArray,QBuffer,QIODevice
from PyQt6.QtGui import QImage

def encode_jpeg(image,quality,backend,profile):
    if backend=='qt':
        start=profile.start()
        data=QByteArray(); buffer=QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        try:
            if not image.save(buffer,'JPG',quality): raise RuntimeError('Qt JPEG encoding failed')
        finally:
            buffer.close()
            profile.finish('jpeg.qt_including_internal_conversion',start)
        return bytes(data)
    if backend!='pillow': raise ValueError('JPEG_ENCODER must be pillow or qt')
    start=profile.start()
    # Preserve native RGB32 painting. Qt performs an exact SIMD channel shuffle;
    # Pillow then maps RGBX without a full RGB24 conversion/copy under the GIL.
    if image.format()!=QImage.Format.Format_RGBX8888:
        image=image.convertToFormat(QImage.Format.Format_RGBX8888)
    bits=image.constBits(); bits.setsize(image.sizeInBytes())
    rgb=Image.frombuffer('RGBX',(image.width(),image.height()),memoryview(bits),'raw','RGBX',image.bytesPerLine(),1)
    profile.finish('convert.rgb32_to_rgbx',start)
    start=profile.start()
    output=io.BytesIO()
    try:
        # Qt switches from 4:2:0 to 4:4:4 above quality 90. Preserve that behavior.
        rgb.save(output,'JPEG',quality=quality,subsampling=0 if quality>90 else 2,
            optimize=False,progressive=False,dpi=(image.logicalDpiX(),image.logicalDpiY()))
        return output.getvalue()
    finally:
        rgb.close()
        profile.finish('jpeg.pillow',start)
