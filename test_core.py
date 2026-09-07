import unittest, tempfile, math
from pathlib import Path
import core

class PhysicalChecks(unittest.TestCase):
    def setUp(self):
        self.c=dict(core.DEFAULT,days=2,start='2026-07-05T00:00:00',warmup_days=0)
    def test_energy_conservation_and_simultaneous_peak(self):
        r=core.simulate(self.c)
        for h in r['hourly']:
            self.assertAlmostEqual(h['hvac_kW'],h['chiller_kW']+h['fan_kW']+h['pump_kW'])
            self.assertAlmostEqual(h['demand_kW'],h['served_kW']+h['unmet_kW'])
            self.assertGreaterEqual(h['served_kW'],0)
            self.assertGreaterEqual(h['unmet_kW'],-1e-8)
        self.assertAlmostEqual(sum(z['served_kWh'] for z in r['zones']),r['kpi']['served_kWh'],places=5)
        self.assertLessEqual(r['kpi']['peak_demand_kW'],sum(z['peak_kW'] for z in r['zones'])+1e-7)
    def test_zero_ageing_equals_healthy(self):
        c=dict(self.c,irreversible_loss_year=0,reversible_loss_1000h=0,coil_loss_1000h=0,filter_loss_1000h=0,pump_loss_1000h=0)
        self.assertEqual(core.simulate(c)['hourly'],core.simulate(c,healthy=True)['hourly'])
    def test_efficiency_loss_increases_power_for_equal_service(self):
        clean=core.simulate(self.c,healthy=True);dirty=core.simulate(dict(self.c,initial_reversible_loss=.2,irreversible_loss_year=0,coil_loss_1000h=0,filter_loss_1000h=0))
        self.assertAlmostEqual(clean['kpi']['served_kWh'],dirty['kpi']['served_kWh'],places=6)
        self.assertGreater(dirty['kpi']['chiller_kWh'],clean['kpi']['chiller_kWh'])
    def test_capacity_limit_and_maintenance_not_rejuvenation(self):
        c=dict(self.c,chiller_kW=10,age_years=20,initial_reversible_loss=.3,trigger=.1,recovery_fraction=1)
        r=core.simulate(c,'S2')
        self.assertGreater(r['kpi']['unmet_kWh'],0)
        self.assertEqual(r['kpi']['maintenance_actions'],1)
        self.assertGreaterEqual(r['hourly'][0]['COP_loss_pct'],100*(1-math.exp(-.005*20))-1e-8)
    def test_measurement_alignment(self):
        r=core.simulate(self.c)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'measured.csv'
            core.write_csv(p,[dict(timestamp=x['timestamp'],hvac_kWh=x['hvac_kW']) for x in r['hourly']])
            m=core.measurement_metrics(r['hourly'],p)
            self.assertEqual(m['RMSE_kWh'],0);self.assertEqual(m['matched_hours'],48)
    def test_reject_bad_inputs(self):
        for c in [dict(self.c,area_m2=-1),dict(self.c,rated_COP=0),dict(self.c,trigger=2)]:
            with self.assertRaises(ValueError):core.simulate(c)
    def test_zone_sum_and_weather_gaps(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'zones.csv';z=core.zone_template(self.c);z[0]['area_m2']+=10;core.write_csv(p,z)
            with self.assertRaises(ValueError):core.zones(dict(self.c,zones_file=str(p)))
            p=Path(d)/'weather.csv';rows=[dict(timestamp=x[0].isoformat(),outdoor_C=x[1],rh_pct=x[2],solar_W_m2=x[3]) for x in core.weather(self.c)]
            rows[2]['timestamp']=rows[1]['timestamp'];core.write_csv(p,rows)
            with self.assertRaises(ValueError):core.weather(dict(self.c,weather_file=str(p)))

if __name__=='__main__':unittest.main(verbosity=2)
