"""Run verification tasks sequentially and save concise machine-readable results."""
import json, subprocess, sys, time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
commands=[['tools/test_pipeline.py'],['tools/test_raster_modes.py'],['tools/test_system.py'],['tools/test_all_sequences.py'],['tools/test_application.py'],['tools/run_isolated.py','tools/test_broadcast_sequence.py'],['tools/compare_visual.py']]
results=[]
for command in commands:
 start=time.perf_counter()
 process=subprocess.run([sys.executable,*command],cwd=root,capture_output=True,text=True)
 result={'command':command,'returncode':process.returncode,'seconds':round(time.perf_counter()-start,3)}
 results.append(result)
 print(json.dumps(result),flush=True)
 if process.returncode: print(process.stdout,process.stderr)
(root/'reports').mkdir(exist_ok=True)
(root/'reports/test-results-v2.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
raise SystemExit(any(result['returncode'] for result in results))
