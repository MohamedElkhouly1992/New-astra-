import argparse,json
from pathlib import Path
import core
p=argparse.ArgumentParser();p.add_argument('--config');p.add_argument('--days',type=int);p.add_argument('--all',action='store_true');p.add_argument('--out',default='results/cli');args=p.parse_args()
c=dict(core.DEFAULT)
if args.config:c.update(json.loads(Path(args.config).read_text(encoding='utf-8-sig')))
if args.days:c['days']=args.days
runs=[]
for s in (['HEALTHY','S0','S1','S2','S3'] if args.all else ['S0']):
    print('Running',s,flush=True);r=core.simulate(c,'S0' if s=='HEALTHY' else s,s=='HEALTHY');runs.append(r);print(json.dumps(r['kpi'],indent=2),flush=True)
print('Saved:',core.export(c,runs,args.out))
