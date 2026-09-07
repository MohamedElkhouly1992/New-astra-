"""Native desktop user interface. No cloud service or API key required."""
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
import threading, queue, json, os, sys, subprocess
from datetime import datetime
from pathlib import Path
import core

LABELS={
 'area_m2':'Total floor area (m²)', 'floors':'Floors (ground included)', 'zones':'Thermal zones',
 'days':'Simulation days', 'setpoint_C':'Cooling setpoint (°C)', 'initial_C':'Initial zone temperature (°C)',
 'chiller_kW':'Rated chiller capacity (kW) — ASSUMED', 'rated_COP':'Reference chiller COP',
 'chw_C':'Prescribed chilled water supply (°C)', 'deltaT_K':'Prescribed water ΔT (K)',
 'pump_kW':'Design pump electric power (kW) — ASSUMED', 'age_years':'Equipment age at start (years)',
 'irreversible_loss_year':'Irreversible COP loss coefficient / year',
 'reversible_loss_1000h':'Recoverable COP loss / 1000 runtime hours',
 'coil_loss_1000h':'Coil capacity loss / 1000 runtime hours',
 'filter_loss_1000h':'Filter state rise / 1000 fan hours',
 'pump_loss_1000h':'Pump efficiency loss / 1000 pump hours',
 'initial_reversible_loss':'Initial recoverable COP loss (0–0.79)',
 'initial_coil_loss':'Initial coil loss (0–0.79)', 'initial_filter_loss':'Initial filter state (0–0.79)',
 'initial_pump_loss':'Initial pump efficiency loss (0–0.79)',
 'maintenance_days':'S1 interval (days)', 'trigger':'S2/S3 deterioration trigger (fraction)',
 'recovery_fraction':'Recoverable state removed by service (fraction)',
 'minimum_gap_days':'Minimum interval between maintenance', 'forecast_hours':'S3 forecast: equivalent operating hours',
 'price_per_kWh':'Electricity price / kWh (your currency)', 'maintenance_cost':'Cost / maintenance action (same currency)',
 'load_multiplier':'Internal and solar gain multiplier', 'warmup_days':'Warmup days'}

class App:
    def __init__(self,root):
        self.root=root;root.title('Engineering College | HVAC Simulation');root.geometry('1200x850')
        self.config=dict(core.DEFAULT);self.vars={};self.results=[];self.q=queue.Queue();self.dest=None
        style=ttk.Style();style.theme_use('clam');style.configure('TButton',padding=7)
        tk.Label(root,text='ENGINEERING COLLEGE  |  HVAC LAB',bg='#0f172a',fg='white',font=('Arial',21,'bold'),anchor='w',padx=20,pady=18).pack(fill='x')
        tk.Label(root,text='17948.4 m²  •  Ground + 3 floors  •  312 zones  •  Chiller + FCUs',font=('Arial',12),pady=8).pack()
        tk.Label(root,text='نموذج أولي قابل للتشغيل — المدخلات الافتراضية ليست قياسات للمبنى — BMS غير متصل',fg='#9a3412',font=('Arial',12)).pack()
        self.nb=ttk.Notebook(root);self.nb.pack(fill='both',expand=True,padx=12,pady=10)
        tabs={name:ttk.Frame(self.nb,padding=12) for name in ['Project','Equipment & ageing','Data & evidence','Results','Charts','Zones']}
        for name,tab in tabs.items():self.nb.add(tab,text=name)
        for k in LABELS:
            group='Project' if k in ['area_m2','floors','zones','days','setpoint_C','initial_C','load_multiplier','warmup_days'] else 'Equipment & ageing'
            self.vars[k]=tk.StringVar(value=str(self.config[k]))
        for group in ['Project','Equipment & ageing']:
            keys=[k for k in LABELS if ('Project' if k in ['area_m2','floors','zones','days','setpoint_C','initial_C','load_multiplier','warmup_days'] else 'Equipment & ageing')==group]
            for i,k in enumerate(keys):
                col=(i//13)*2;row=i%13
                ttk.Label(tabs[group],text=LABELS[k]).grid(row=row,column=col,sticky='w',padx=5,pady=6)
                ttk.Entry(tabs[group],textvariable=self.vars[k],width=12).grid(row=row,column=col+1,padx=8,pady=6)
        p=tabs['Project'];ttk.Button(p,text='Save project JSON',command=self.save_config).grid(row=10,column=0,pady=8)
        ttk.Button(p,text='Load project JSON',command=self.load_config).grid(row=10,column=1)
        ttk.Label(p,text='S0: no maintenance\nS1: scheduled maintenance\nS2: state-triggered maintenance\nS3: linear forecast-triggered maintenance\nHEALTHY: same inputs with all ageing disabled\n\nStart date and advanced coefficients are editable in project JSON.\nInputs use SI units. Friday/Saturday are the default weekend.\nAll 312 zones start as equal-area placeholders; import actual zone data.').grid(row=11,column=0,columnspan=3,sticky='w',pady=15)
        d=tabs['Data & evidence'];self.data_label=tk.StringVar();
        for i,(text,cmd) in enumerate([
            ('Import hourly weather CSV / EPW',self.load_weather),('Import 312-zone CSV',self.load_zones),
            ('Export editable zone template',self.template),('Use demonstration data',self.reset_data),
            ('Inspect DesignBuilder daily reference',self.reference),('Compare measured hourly BMS CSV',self.bms),
            ('Open Arabic guide',self.guide)]):
            ttk.Button(d,text=text,command=cmd).grid(row=i,column=0,sticky='ew',pady=6)
        ttk.Label(d,textvariable=self.data_label,wraplength=740).grid(row=0,column=1,rowspan=4,padx=20,sticky='nw')
        ttk.Label(d,text='Weather CSV: timestamp,outdoor_C,rh_pct,solar_W_m2\nBMS CSV: timestamp,hvac_kWh (energy over a one-hour interval)\nUse the same timestamp convention and local clock.\nEPW: rows are mapped sequentially from project start; align start to Jan 1.\nDaily reference is not used as an hourly load profile.\nNo calibration or BMS connection is implied.').grid(row=5,column=1,rowspan=3,padx=20,sticky='nw')
        r=tabs['Results'];self.report=tk.Text(r,wrap='word',font=('Consolas',11));self.report.pack(fill='both',expand=True)
        self.canvas=tk.Canvas(tabs['Charts'],bg='#0f172a');self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda e:self.draw())
        ztab=tabs['Zones'];self.zone_case=tk.StringVar(value='S0')
        self.zone_picker=ttk.Combobox(ztab,textvariable=self.zone_case,values=['S0'],state='readonly');self.zone_picker.pack(anchor='w',pady=6)
        self.zone_picker.bind('<<ComboboxSelected>>',lambda e:self.show_zones())
        cols=['zone_id','floor','area_m2','peak_kW','demand_kWh','served_kWh','unmet_kWh','max_C','overheat_hours']
        self.zone_table=ttk.Treeview(ztab,columns=cols,show='headings')
        for col in cols:self.zone_table.heading(col,text=col);self.zone_table.column(col,width=115,anchor='center')
        sc=ttk.Scrollbar(ztab,orient='vertical',command=self.zone_table.yview);sc.pack(side='right',fill='y')
        self.zone_table.configure(yscrollcommand=sc.set);self.zone_table.pack(fill='both',expand=True)
        bar=ttk.Frame(root,padding=10);bar.pack(fill='x');self.strategy=tk.StringVar(value='S0')
        ttk.Combobox(bar,textvariable=self.strategy,values=['S0','S1','S2','S3'],state='readonly',width=6).pack(side='left')
        self.run_btn=ttk.Button(bar,text='Run selected',command=lambda:self.run(False));self.run_btn.pack(side='left',padx=5)
        self.all_btn=ttk.Button(bar,text='Compare HEALTHY + S0–S3',command=lambda:self.run(True));self.all_btn.pack(side='left',padx=5)
        ttk.Button(bar,text='Open exported results',command=self.open_results).pack(side='left',padx=5)
        self.status=tk.StringVar(value='Ready • demonstration assumptions loaded');ttk.Label(bar,textvariable=self.status).pack(side='right')
        self.update_data();root.after(200,self.poll)
    def get_config(self):
        c=dict(self.config)
        for k,v in self.vars.items():c[k]=float(v.get())
        for k in ['zones','floors','days','warmup_days']:
            if int(c[k])!=c[k]:raise ValueError(k+' must be integer')
            c[k]=int(c[k])
        core.validate(c);return c
    def update_data(self):
        self.data_label.set('Weather: '+(self.config['weather_file'] or 'SYNTHETIC, illustrative climate only')+'\n\nZones: '+(self.config['zones_file'] or 'UNVERIFIED equal-area placeholders')+'\n\nPrior daily reference: 2020–2024 DesignBuilder simulations.\nArea conflict in prior MATLAB file: 17994.3 m²; current project uses your latest 17948.4 m². Historical daily reference is preserved, not rescaled.')
    def load_weather(self):
        p=filedialog.askopenfilename(filetypes=[('Weather','*.csv *.epw')])
        if p:self.config['weather_file']=p;self.update_data()
    def load_zones(self):
        p=filedialog.askopenfilename(filetypes=[('Zones','*.csv')])
        if p:self.config['zones_file']=p;self.update_data()
    def reset_data(self):
        self.config['zones_file']='';self.config['weather_file']='';self.update_data()
    def template(self):
        try:
            c=self.get_config();p=filedialog.asksaveasfilename(defaultextension='.csv',initialfile='zone_inputs.csv')
            if p:core.write_csv(p,core.zone_template(c))
        except Exception as e:messagebox.showerror('Inputs',str(e))
    def save_config(self):
        try:
            c=self.get_config();p=filedialog.asksaveasfilename(defaultextension='.json')
            if p:Path(p).write_text(json.dumps(c,indent=2),encoding='utf-8')
        except Exception as e:messagebox.showerror('Project',str(e))
    def load_config(self):
        p=filedialog.askopenfilename(filetypes=[('Project','*.json')])
        if not p:return
        try:
            c=dict(core.DEFAULT);c.update(json.loads(Path(p).read_text(encoding='utf-8-sig')));core.validate(c)
            self.config=c
            for k,v in self.vars.items():v.set(str(c[k]))
            self.update_data()
        except Exception as e:messagebox.showerror('Project',str(e))
    def run(self,all_runs):
        try:c=self.get_config();core.zones(c);core.weather(c)
        except Exception as e:messagebox.showerror('Input validation',str(e));return
        self.run_btn.state(['disabled']);self.all_btn.state(['disabled']);self.status.set('Running…')
        selected=self.strategy.get()
        def work():
            try:
                runs=[]
                for s in (['HEALTHY','S0','S1','S2','S3'] if all_runs else [selected]):
                    self.q.put(('status','Running '+s));runs.append(core.simulate(c,'S0' if s=='HEALTHY' else s,s=='HEALTHY'))
                folder=core.ROOT/'results'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                core.export(c,runs,folder);self.q.put(('done',(runs,folder)))
            except Exception as e:self.q.put(('error',str(e)))
        threading.Thread(target=work,daemon=True).start()
    def poll(self):
        try:
            while True:
                key,value=self.q.get_nowait()
                if key=='status':self.status.set(value)
                else:
                    self.run_btn.state(['!disabled']);self.all_btn.state(['!disabled'])
                    if key=='error':self.status.set('Failed');messagebox.showerror('Simulation',value)
                    else:
                        self.results,self.dest=value;self.status.set('Completed • CSV, SVG and audit exported')
                        self.report.delete('1.0','end')
                        self.report.insert('end','SIMULATED ESTIMATES — NOT FIELD VALIDATION\nRead evidence_manifest.json for assumptions.\n\n')
                        for run in self.results:
                            self.report.insert('end',json.dumps(run['kpi'],indent=2)+'\n\n')
                        self.report.insert('end','Compare served cooling and overheating before interpreting lower electricity as efficiency improvement.\nExport: '+str(self.dest))
                        self.zone_picker['values']=[r['kpi']['strategy'] for r in self.results]
                        self.zone_case.set(self.results[0]['kpi']['strategy']);self.show_zones()
                        self.nb.select(3);self.draw()
        except queue.Empty:pass
        self.root.after(200,self.poll)
    def draw(self):
        c=self.canvas;c.delete('all');w=max(500,c.winfo_width());h=max(300,c.winfo_height())
        c.create_text(25,25,text='Monthly HVAC electricity (kWh) — simulated',fill='white',anchor='w',font=('Arial',16))
        if not self.results:return
        seq=[]
        for run in self.results:
            m={}
            for r in run['hourly']:m[r['timestamp'][:7]]=m.get(r['timestamp'][:7],0)+r['hvac_kW']
            seq.append(list(m.values()))
        ymax=max(1,max(max(v) for v in seq));n=max(map(len,seq));colors=['#94a3b8','#ef4444','#f59e0b','#22c55e','#38bdf8']
        for i in range(5):
            y=h-75-i*(h-145)/4;c.create_line(75,y,w-25,y,fill='#334155');c.create_text(65,y,text=f'{ymax*i/4:.0f}',fill='white',anchor='e')
        for k,vals in enumerate(seq):
            pts=[]
            for i,v in enumerate(vals):pts.extend([75+i*(w-100)/max(1,n-1),h-75-v/ymax*(h-145)])
            if len(pts)>2:c.create_line(*pts,fill=colors[k],width=3)
            else:c.create_oval(pts[0]-3,pts[1]-3,pts[0]+3,pts[1]+3,fill=colors[k])
            c.create_text(90+k*160,h-30,text=self.results[k]['kpi']['strategy'],fill=colors[k],anchor='w')
    def reference(self):
        self.report.delete('1.0','end');self.report.insert('end','DAILY DESIGNBUILDER REFERENCE — SIMULATED, NOT MEASURED\nOriginal export preserved; not scaled to revised floor area.\nDaily sums do not identify hourly peak loads.\n\n'+json.dumps(core.reference_summary(),indent=2));self.nb.select(3)
    def show_zones(self):
        self.zone_table.delete(*self.zone_table.get_children())
        run=next((r for r in self.results if r['kpi']['strategy']==self.zone_case.get()),None)
        if run:
            for z in run['zones']:
                self.zone_table.insert('','end',values=[f'{z[k]:.2f}' if isinstance(z[k],float) else z[k] for k in self.zone_table['columns']])
    def bms(self):
        if not self.results:messagebox.showinfo('BMS','Run a simulation first.');return
        p=filedialog.askopenfilename(filetypes=[('Measurements','*.csv')])
        if not p:return
        try:
            metrics={r['kpi']['strategy']:core.measurement_metrics(r['hourly'],p) for r in self.results}
            self.report.insert('end','\nBMS comparison\n'+json.dumps(metrics,indent=2));self.nb.select(3)
            (self.dest/'measurement_comparison.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
        except Exception as e:messagebox.showerror('BMS',str(e))
    def open_path(self,p):
        if sys.platform=='win32':os.startfile(str(p))
        else:subprocess.Popen(['open' if sys.platform=='darwin' else 'xdg-open',str(p)])
    def open_results(self):
        if self.dest:self.open_path(self.dest)
    def guide(self):self.open_path(core.ROOT/'README_AR.txt')

if __name__=='__main__':
    root=tk.Tk();App(root);root.mainloop()
