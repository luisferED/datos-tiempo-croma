import os, runpy, sys, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as c
with tempfile.TemporaryDirectory() as temp:
 c.RUTA_BASE_DATOS=Path(temp)/'test.sqlite3'
 runpy.run_path(sys.argv[1],run_name='__main__')
