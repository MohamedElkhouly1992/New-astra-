"""Transparent reduced-order cooling simulator. Python standard library only."""
import csv, json, math, hashlib, statistics
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT = dict(area_m2=17948.4, floors=4, zones=312, days=365,
    start='2026-01-01T00:00:00', setpoint_C=24., initial_C=24.,
    chiller_kW=1600., rated_COP=5.5, chw_C=6., deltaT_K=4.,
    min_plr=0.1, cop_temp_slope=0.025, capacity_temp_slope=0.01,
    pump_kW=15., pump_min_flow=0.2, age_years=0.,
    irreversible_loss_year=0.005, reversible_loss_1000h=0.01,
    coil_loss_1000h=0.02, filter_loss_1000h=0.04, pump_loss_1000h=0.005,
    initial_reversible_loss=0., initial_coil_loss=0., initial_filter_loss=0.,
    initial_pump_loss=0., maintenance_days=180, trigger=0.15,
    recovery_fraction=0.8, minimum_gap_days=30, forecast_hours=168,
    price_per_kWh=0., maintenance_cost=0., load_multiplier=1.,
    weather_file='', zones_file='', warmup_days=7)

def read_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as f: return list(csv.DictReader(f))

def write_csv(path, rows):
    if not rows: return
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def validate(c):
    for k,v in c.items():
        if isinstance(v,(float,int)) and not math.isfinite(v): raise ValueError(k+' must be finite')
    for k in ['area_m2','chiller_kW','rated_COP','deltaT_K','maintenance_days','minimum_gap_days']:
        if c[k]<=0: raise ValueError(k+' must be positive')
    for k in ['days','floors','zones','warmup_days']:
        if int(c[k])!=c[k] or c[k] < (0 if k=='warmup_days' else 1): raise ValueError(k+' invalid integer')
    if c['days']>3660 or c['zones']>2000: raise ValueError('Limit: 3660 days, 2000 zones')
    for k in ['min_plr','pump_min_flow','recovery_fraction','trigger']:
        if not 0<c[k]<=1: raise ValueError(k+' must be in (0,1]')
    for k in ['initial_reversible_loss','initial_coil_loss','initial_filter_loss','initial_pump_loss']:
        if not 0<=c[k]<0.8: raise ValueError(k+' must be in [0,0.8)')
    for k in ['pump_kW','age_years','irreversible_loss_year','reversible_loss_1000h','coil_loss_1000h','filter_loss_1000h','pump_loss_1000h','price_per_kWh','maintenance_cost','forecast_hours','load_multiplier','cop_temp_slope','capacity_temp_slope']:
        if c[k]<0: raise ValueError(k+' must be nonnegative')
    if not 10<=c['setpoint_C']<=35: raise ValueError('Setpoint must be 10–35 C')
    datetime.fromisoformat(c['start'])

def zone_template(c):
    # Uniform placeholders, not reconstructed as-built geometry.
    a=c['area_m2']/c['zones']
    return [dict(zone_id=f'Z{i+1:03}',floor=min(c['floors']-1,i*c['floors']//c['zones']),
        area_m2=a, height_m=3.5, envelope_UA_W_K=a*2., capacitance_kJ_K=a*150.,
        solar_aperture_m2=a*.08, people=a*.111, lighting_W_m2=8., equipment_W_m2=11.73,
        outdoor_air_L_s_person=10., infiltration_ACH=.2, heat_recovery_sensible=0.,
        heat_recovery_latent=0., fcu_kW=a*.1, fan_W=a*2.,
        occupied_start=8,occupied_end=17,weekend='4|5',input_status='ASSUMED_UNVERIFIED') for i in range(c['zones'])]

def zones(c):
    z=read_csv(c['zones_file']) if c['zones_file'] else zone_template(c)
    if len(z)!=c['zones']: raise ValueError('Zone count does not match configuration')
    if len({x['zone_id'] for x in z})!=len(z): raise ValueError('Duplicate zone IDs')
    for x in z:
        for k in zone_template(dict(c,zones=1))[0]:
            if k not in x: raise ValueError('Missing zone column: '+k)
            if k not in ['zone_id','weekend','input_status']: x[k]=float(x[k])
        for k in ['area_m2','height_m','envelope_UA_W_K','capacitance_kJ_K','fcu_kW']:
            if not math.isfinite(x[k]) or x[k]<=0: raise ValueError('Invalid '+k)
        for k,v in x.items():
            if isinstance(v,float) and (not math.isfinite(v) or v<0): raise ValueError('Invalid '+k)
        if int(x['floor'])!=x['floor'] or x['floor']>=c['floors']: raise ValueError('Invalid floor')
        if not 0<=x['occupied_start']<x['occupied_end']<=24: raise ValueError('Invalid schedule')
        if any(q not in '0123456' for q in x['weekend'].split('|') if q): raise ValueError('Weekend: weekday numbers 0–6 separated by |')
        if x['heat_recovery_sensible']>1 or x['heat_recovery_latent']>1: raise ValueError('Recovery must be 0–1')
    if abs(sum(x['area_m2'] for x in z)-c['area_m2'])>.1: raise ValueError('Zone areas must sum to building area within 0.1 m2')
    return z

def weather(c):
    if c['weather_file']:
        p=Path(c['weather_file'])
        if p.suffix.lower()=='.epw':
            with open(p,encoding='utf-8-sig') as f: raw=list(csv.reader(f))[8:]
            raw=[dict(timestamp=(datetime(2001,int(x[1]),int(x[2]))+timedelta(hours=int(x[3])-1)).isoformat(),
                      outdoor_C=x[6],rh_pct=x[8],solar_W_m2=x[13]) for x in raw if int(x[1])!=2 or int(x[2])!=29]
            # EPW typical-year calendar is mapped explicitly to simulation start.
            for i,x in enumerate(raw): x['timestamp']=(datetime.fromisoformat(c['start'])+timedelta(hours=i)).isoformat()
        else: raw=read_csv(p)
        n=int(c['days']*24)
        if len(raw)<n: raise ValueError('Weather must contain at least days × 24 hourly rows')
        out=[]
        for i,r in enumerate(raw[:n]):
            t=datetime.fromisoformat(r['timestamp'])
            if i and t-out[-1][0]!=timedelta(hours=1): raise ValueError('Weather timestamps must be consecutive hourly values')
            v=[float(r[k]) for k in ['outdoor_C','rh_pct','solar_W_m2']]
            if not all(math.isfinite(a) for a in v) or not -60<=v[0]<=65 or not 0<=v[1]<=100 or not 0<=v[2]<=1500: raise ValueError('Weather invalid/missing EPW values')
            out.append((t,*v))
        return out
    t0=datetime.fromisoformat(c['start'])
    return [(t0+timedelta(hours=i),22+8*math.sin(2*math.pi*((t0+timedelta(hours=i)).timetuple().tm_yday-105)/365)+4*math.sin(2*math.pi*(i%24-9)/24),
             60.,max(0.,750*math.sin(math.pi*(i%24-6)/12))) for i in range(int(c['days']*24))]

def humidity_ratio(t,rh):
    p=min(100000.,610.94*math.exp(17.625*t/(t+243.04))*rh/100)
    return .62198*p/(101325-p)

def simulate(c,strategy='S0',healthy=False):
    validate(c)
    if strategy not in ['S0','S1','S2','S3']: raise ValueError('Unknown strategy')
    zz=zones(c); ww=weather(c); temps=[c['initial_C']]*len(zz)
    zr=[dict(zone_id=z['zone_id'],floor=int(z['floor']),area_m2=z['area_m2'],demand_kWh=0.,served_kWh=0.,unmet_kWh=0.,peak_kW=0.,max_C=-100.,occupied_hours=0,overheat_hours=0) for z in zz]
    rev=c['initial_reversible_loss']; coil=c['initial_coil_loss']; filt=c['initial_filter_loss']; pump=c['initial_pump_loss']
    if healthy: rev=coil=filt=pump=0.
    out=[]; last=-1e9; actions=0; runtime=0.; events=[]
    warm=min(len(ww),int(c['warmup_days']*24))
    sequence=list(enumerate(ww[:warm],-warm))+list(enumerate(ww))
    for step,(t,to,rh,solar) in sequence:
        # Warmup repeats initial weather; no ageing, events, or reported energy.
        wear=0. if healthy else min(.5,1-math.exp(-c['irreversible_loss_year']*(c['age_years']+max(0,step)/8760)))
        loss=1-(1-wear)*(1-rev)
        forecast=c['forecast_hours']/1000*max(c['reversible_loss_1000h'],c['coil_loss_1000h'],c['filter_loss_1000h'])
        health=max(rev,coil,filt,pump)
        due=(strategy=='S1' and step-last>=c['maintenance_days']*24 and step>=c['maintenance_days']*24) or (strategy=='S2' and health>=c['trigger']) or (strategy=='S3' and health+forecast>=c['trigger'])
        if step>=0 and not healthy and due and step-last>=c['minimum_gap_days']*24:
            old=health; factor=1-c['recovery_fraction']; rev*=factor; coil*=factor; filt*=factor; pump*=factor
            last=step;actions+=1;events.append(dict(timestamp=t.isoformat(),strategy=strategy,recoverable_state_before=old,recovery_fraction=c['recovery_fraction']))
            loss=1-(1-wear)*(1-rev)
        qs=[]; ql=[]; caps=[]; free=[]; response=[]; fans=[]; occupied=[]
        for j,z in enumerate(zz):
            occ=z['occupied_start']<=t.hour<z['occupied_end'] and str(t.weekday()) not in z['weekend'].split('|')
            occupied.append(occ)
            flow=z['outdoor_air_L_s_person']*z['people']/1000*occ
            leak=z['infiltration_ACH']*z['area_m2']*z['height_m']/3600
            ua=z['envelope_UA_W_K']+1206*(flow*(1-z['heat_recovery_sensible'])+leak)
            capacitance=z['capacitance_kJ_K']*1000
            decay=math.exp(-ua*3600/capacitance); b=(1-decay)/ua
            fan=z['fan_W']*occ
            gain=c['load_multiplier']*(occ*(z['people']*75+z['area_m2']*(z['lighting_W_m2']+z['equipment_W_m2']))+solar*z['solar_aperture_m2'])+fan
            tf=to+(temps[j]-to)*decay+gain*b
            sensible=max(0.,(tf-c['setpoint_C'])/b/1000) if occ else 0.
            latent=max(0.,1.2*(flow*(1-z['heat_recovery_latent'])+leak)*2501000*(humidity_ratio(to,rh)-humidity_ratio(c['setpoint_C'],50))/1000+z['people']*.055*c['load_multiplier']) if occ else 0.
            qs.append(sensible);ql.append(latent);free.append(tf);response.append(b)
            caps.append(z['fcu_kW']*(1-coil)*(1-.5*filt)*occ);fans.append(fan/1000)
        demand=sum(qs)+sum(ql)
        requests=[min(a+b,cap) for a,b,cap in zip(qs,ql,caps)]
        available=c['chiller_kW']*max(.3,1-c['capacity_temp_slope']*(to-35))*(1-wear)
        served=min(sum(requests),available,demand); share=served/sum(requests) if sum(requests)>0 else 0.
        plr=served/available if available else 0.
        eir_temp=max(.3,1+c['cop_temp_slope']*(to-35))
        # Explicit generic part-load proxy, not fitted manufacturer EIR curves.
        operating=max(c['min_plr'],plr); eir_plr=.15+.7*operating+.15*operating**2
        cycling=plr/operating if plr else 0.
        pch=available/c['rated_COP']*eir_temp*eir_plr*cycling/max(.05,1-loss)
        flowfraction=max(c['pump_min_flow'],served/c['chiller_kW']) if served else 0.
        pp=c['pump_kW']*flowfraction**3/max(.1,1-pump)
        pf=sum(fans); total=pch+pp+pf
        for j,z in enumerate(zz):
            actual=requests[j]*share; fraction=qs[j]/(qs[j]+ql[j]) if qs[j]+ql[j]>0 else 0
            temps[j]=free[j]-actual*fraction*1000*response[j]
            if step>=0:
                r=zr[j];r['demand_kWh']+=qs[j]+ql[j];r['served_kWh']+=actual
                r['unmet_kWh']+=qs[j]+ql[j]-actual;r['peak_kW']=max(r['peak_kW'],qs[j]+ql[j]);r['max_C']=max(r['max_C'],temps[j])
                r['occupied_hours']+=int(occupied[j]);r['overheat_hours']+=int(occupied[j] and temps[j]>c['setpoint_C']+1)
        if step>=0:
            out.append(dict(timestamp=t.isoformat(),outdoor_C=to,demand_kW=demand,served_kW=served,unmet_kW=demand-served,chiller_kW=pch,fan_kW=pf,pump_kW=pp,hvac_kW=total,COP=served/pch if pch else 0.,system_COP=served/total if total else 0.,mean_zone_C=sum(x*z['area_m2'] for x,z in zip(temps,zz))/c['area_m2'],max_zone_C=max(temps),COP_loss_pct=loss*100,coil_capacity_loss_pct=coil*100,filter_state_pct=filt*100,pump_efficiency_loss_pct=pump*100,chw_supply_C=c['chw_C'],chw_return_C=c['chw_C']+c['deltaT_K'] if served else c['chw_C'],water_kg_s=served/(4.18*c['deltaT_K']),maintenance_count=actions))
            if not healthy:
                run=cycling if served else 0.;runtime+=run
                rev=min(.5,rev+c['reversible_loss_1000h']*run/1000)
                coil=min(.7,coil+c['coil_loss_1000h']*run/1000)
                filt=min(.7,filt+c['filter_loss_1000h']*int(pf>0)/1000)
                pump=min(.5,pump+c['pump_loss_1000h']*int(pp>0)/1000)
    energy=sum(r['hvac_kW'] for r in out);cooling=sum(r['served_kW'] for r in out); ec=sum(r['chiller_kW'] for r in out)
    kpi=dict(strategy='HEALTHY' if healthy else strategy,hours=len(out),demand_kWh=sum(r['demand_kW'] for r in out),served_kWh=cooling,unmet_kWh=sum(r['unmet_kW'] for r in out),peak_demand_kW=max(r['demand_kW'] for r in out),peak_demand_TR=max(r['demand_kW'] for r in out)/3.51685284,chiller_kWh=ec,fan_kWh=sum(r['fan_kW'] for r in out),pump_kWh=sum(r['pump_kW'] for r in out),hvac_kWh=energy,period_EUI_kWh_m2=energy/c['area_m2'],seasonal_chiller_COP=cooling/ec if ec else 0.,seasonal_system_COP=cooling/energy if energy else 0.,maintenance_actions=actions,operating_cost=energy*c['price_per_kWh']+actions*c['maintenance_cost'],occupied_zone_hours=sum(r['occupied_hours'] for r in zr),overheated_zone_hours=sum(r['overheat_hours'] for r in zr),final_COP_loss_pct=out[-1]['COP_loss_pct'])
    return dict(hourly=out,zones=zr,kpi=kpi,events=events)

def reference_summary(path=ROOT/'data/designbuilder_daily.csv'):
    rows=read_csv(path); result=[]
    for year in sorted({r['Year'] for r in rows}):
        rr=[r for r in rows if r['Year']==year]
        s={k:sum(float(r[k]) for r in rr) for k in ['CoolingThermal_kWh','CoolingElectricity_kWh','HVACElectricity_kWh','SystemFans_kWh','SystemPumps_kWh']}
        result.append(dict(year=year,records=len(rr),**s,ratio_thermal_to_chiller_electricity=s['CoolingThermal_kWh']/s['CoolingElectricity_kWh']))
    return result

def measurement_metrics(predicted,path):
    """Exact timestamp alignment; input is hourly interval energy, no extrapolation."""
    rows=read_csv(path);seen=set();pairs=[]; index={r['timestamp']:r for r in predicted}
    for r in rows:
        key=datetime.fromisoformat(r['timestamp']).isoformat()
        if key in seen: raise ValueError('Duplicate measured timestamps')
        seen.add(key)
        if key in index:
            y=float(r['hvac_kWh'])
            if not math.isfinite(y) or y<0: raise ValueError('Measured energy must be nonnegative')
            pairs.append((y,index[key]['hvac_kW']))
    if len(pairs)<2: raise ValueError('Need at least two matching hourly measurements')
    n=len(pairs);mean=statistics.mean(y for y,p in pairs);rmse=math.sqrt(sum((p-y)**2 for y,p in pairs)/n)
    return dict(matched_hours=n,measurement_rows=len(rows),prediction_hours=len(predicted),RMSE_kWh=rmse,CVRMSE_pct=100*rmse/mean if mean else None,NMBE_pct=100*sum(p-y for y,p in pairs)/(n*mean) if mean else None,note='n denominator; fixed predictions; no fitted-parameter correction; matching intervals only')

def svg_chart(path, runs):
    colors=['#94a3b8','#ef4444','#f59e0b','#22c55e','#38bdf8']; w=1000;h=430
    s=['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="430" viewBox="0 0 1000 430"><rect width="1000" height="430" fill="#0f172a"/><g font-family="Arial" fill="white"><text x="60" y="30" font-size="20">Monthly HVAC electricity (kWh) — simulation</text>']
    series=[]
    for run in runs:
        months={}
        for r in run['hourly']: months[r['timestamp'][:7]]=months.get(r['timestamp'][:7],0)+r['hvac_kW']
        series.append(list(months.values()))
    maximum=max(1,max(max(x) for x in series));n=max(len(x) for x in series)
    for i in range(5):
        y=340-i*65;s.append(f'<path d="M60 {y}H950" stroke="#334155"/><text x="5" y="{y}">{maximum*i/4:.0f}</text>')
    for k,(vals,run) in enumerate(zip(series,runs)):
        pts=' '.join(f'{60+i*890/max(1,n-1):.1f},{340-v/maximum*260:.1f}' for i,v in enumerate(vals))
        s.append(f'<polyline points="{pts}" fill="none" stroke="{colors[k%5]}" stroke-width="3"/><text x="{60+k*175}" y="400" fill="{colors[k%5]}">{run["kpi"]["strategy"]}</text>')
    s.append('<text x="450" y="365">Month index from start</text></g></svg>');Path(path).write_text(''.join(s),encoding='utf-8')

def export(c,runs,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    for r in runs:
        p=folder/r['kpi']['strategy'];p.mkdir(exist_ok=True)
        write_csv(p/'hourly.csv',r['hourly']);write_csv(p/'zones.csv',r['zones']);write_csv(p/'maintenance.csv',r['events'])
    write_csv(folder/'comparison.csv',[r['kpi'] for r in runs]);write_csv(folder/'designbuilder_reference.csv',reference_summary())
    write_csv(folder/'zone_inputs.csv',zones(c))
    write_csv(folder/'weather_used.csv',[dict(timestamp=t.isoformat(),outdoor_C=a,rh_pct=b,solar_W_m2=d) for t,a,b,d in weather(c)])
    (folder/'config.json').write_text(json.dumps(c,indent=2),encoding='utf-8')
    svg_chart(folder/'monthly_energy.svg',runs)
    audit=dict(model='Hourly 312-zone 1R1C cooling prototype, NOT EnergyPlus',field_validated=False,
        weather='IMPORTED_UNVERIFIED' if c['weather_file'] else 'SYNTHETIC_DEMONSTRATION',
        zones='IMPORTED_UNVERIFIED' if c['zones_file'] else 'UNIFORM_PLACEHOLDER_GEOMETRY',
        reference='Prior DesignBuilder daily export, simulated not measured; no automatic calibration',
        limits=['Cooling only; no boiler/heating simulation','Ideal setpoint control and proportional sensible/latent service; no moisture state',
        'Fixed-speed fan power; filter state reduces coil delivery; no fan-curve or hydraulic network solution',
        'Generic temperature/part-load response, no manufacturer curve calibration',
        'CHW supply and delta T are prescribed; no water-loop transient',
        'S3 is an explicit linear deterioration forecast policy, not trained AI',
        'Degradation rates are assumed; chronological wear cannot be fully removed by maintenance',
        'Compare energy jointly with cooling served, unmet load and overheating; reduced service is not efficiency savings'],
        hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [folder/'config.json',folder/'zone_inputs.csv',folder/'weather_used.csv',ROOT/'core.py']})
    (folder/'evidence_manifest.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    return folder
