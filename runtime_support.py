"""Bounded HTTP resources, image validation and explicitly closed SQLite connections."""
import contextlib
import io
import os
import sqlite3
import threading
import warnings
from http.server import ThreadingHTTPServer as _HTTPServer
from PIL import Image

@contextlib.contextmanager
def database(path, timeout=3):
    connection = sqlite3.connect(path, timeout=timeout)
    try:
        with connection:
            yield connection
    finally:
        connection.close()

class BoundedHTTPServer(_HTTPServer):
    daemon_threads = True
    block_on_close = False
    def __init__(self, *args, **kwargs):
        self.slots = threading.BoundedSemaphore(max(1, min(128, int(os.environ.get('MAX_HTTP_CONNECTIONS','24')))))
        super().__init__(*args, **kwargs)
    def process_request(self, request, address):
        request.settimeout(10)
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request,address)
        except BaseException:
            self.slots.release()
            raise
    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request,address)
        finally:
            self.slots.release()

def validate_image(data, extension):
    formats = {'.png':'PNG','.jpg':'JPEG','.jpeg':'JPEG','.webp':'WEBP','.bmp':'BMP'}
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.format != formats[extension] or image.width*image.height > 20_000_000:
                    raise ValueError('Formato o dimensiones de imagen no permitidos (máximo 20 MP).')
                image.verify()
        except Exception as exc:
            raise ValueError('Imagen inválida o demasiado grande.') from exc


def configure_render_affinity(value):
    """Optional Linux process binding, restricted to CPUs already allowed by the host."""
    if not value or not value.strip(): return None
    if not hasattr(os,'sched_setaffinity'):
        raise RuntimeError('RENDER_CPU_AFFINITY requires Linux; use benchmark --affinity on Windows')
    requested={int(part.strip()) for part in value.split(',')}
    if not requested or not requested.issubset(os.sched_getaffinity(0)):
        raise ValueError('Requested render CPUs are outside the allowed affinity mask')
    os.sched_setaffinity(0,requested)
    return sorted(requested)
