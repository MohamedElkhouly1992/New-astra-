"""Run an existing, version-compatible IDF using installed EnergyPlus.
Does NOT generate the actual building geometry or connect the prototype to E+.
"""
import argparse,subprocess,json,hashlib
from pathlib import Path
from datetime import datetime
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--exe',required=True);p.add_argument('--idf',required=True);p.add_argument('--epw',required=True);p.add_argument('--out',required=True)
a=p.parse_args();exe=Path(a.exe).resolve();idf=Path(a.idf).resolve();epw=Path(a.epw).resolve();out=Path(a.out).resolve()
for f in [exe,idf,epw]:
    if not f.is_file():p.error('File not found: '+str(f))
if out.exists() and any(out.iterdir()):p.error('Choose a new or empty output folder to preserve prior results')
out.mkdir(parents=True,exist_ok=True)
version=subprocess.run([str(exe),'--version'],capture_output=True,text=True)
command=[str(exe),'-w',str(epw),'-d',str(out),'-r',str(idf)]
with open(out/'runner_stdout.txt','w',encoding='utf-8') as log:
    result=subprocess.run(command,cwd=idf.parent,stdout=log,stderr=subprocess.STDOUT)
manifest=dict(timestamp=datetime.now().isoformat(),engine_version=version.stdout.strip(),command=command,returncode=result.returncode,
    hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [idf,epw]},note='Review eplusout.err severe warnings, convergence, sizing and unmet hours. Completion alone is not validation. External schedule files are not hashed automatically.')
(out/'run_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('EnergyPlus exit code:',result.returncode,'; results:',out)
raise SystemExit(result.returncode)
