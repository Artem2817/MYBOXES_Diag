"""Deterministic demonstration peer. Every frame identifies simulation, never real evidence."""
from pathlib import Path
import json,math,re,time
from .protocol import Frame
class DemoPeer:
    def __init__(self,profile='MyboxH743_mini_v2_vib'):
        self.profile=json.loads((Path(__file__).parent/'profiles'/f'{profile}.json').read_text(encoding='utf-8'));self.started=time.monotonic();self.seq=0;self.rate=20;self.last_stream=0;self.results={}
        catalog=Path(__file__).parent/'test_catalog.json';self.tests=json.loads(catalog.read_text(encoding='utf-8'))
        n=self.profile['index']
        for t in self.tests:
            k=t['test'];t['applicable']=not ((k.startswith(('imu1','baro1')) or k=='imu.compare') and n!=2 or k=='pwm14.scope' and n!=0 or k in ('heater.external','buzzer.audio') and n==0)
    def frame(self,kind,body):
        self.seq+=1;body['demo']=True;return Frame(kind,self.seq,int((time.monotonic()-self.started)*1000),body)
    def request(self,c):
        op=c['op'];out=[]
        if op=='info':out.append(self.frame(2,dict(id=c['id'],ok=True,op='info',profile=self.profile['id'],revision_source='build_profile',hardware_revision=None,mcu='SIMULATED STM32H743xx',uid='DEMO-NO-PHYSICAL-BOARD',firmware='MyboxDiag DEMO 0.2.2',build_id='simulation',protocol=1,uptime_ms=int((time.monotonic()-self.started)*1000),test_count=len(self.tests),imu_count=len(self.profile['imus']),barometer_count=len(self.profile['barometers']),orientation_source='hardware_profile')))
        else:out.append(self.frame(2,dict(id=c['id'],ok=True,code='DEMO_OK')))
        if op=='list':
            out.extend(self.frame(3,dict(event='test',**t)) for t in self.tests);out.append(self.frame(3,dict(event='list_complete')))
        elif op=='results':out.extend(self.frame(3,r.copy()) for r in self.results.values());out.append(self.frame(3,dict(event='results_complete')))
        elif op=='stream':self.rate=max(0,min(100,c.get('rate',20)))
        elif op=='run':
            for t in self.tests:
                if c.get('test') not in ('all',t['test']):continue
                state='not_applicable' if not t['applicable'] else 'passed' if t['automatic'] else 'needs_action'
                if 'selftest' in t['test'] or t['test']=='flash.write':state='warning' if t['applicable'] else 'not_applicable'
                r=dict(event='result',test=t['test'],state=state,code='DEMO_SIMULATED',detail='Демонстрация: синтетический результат, физическая плата не проверялась',expected='Синтетические демонстрационные данные',actual='Симулятор',duration_ms=1500)
                self.results[t['test']]=r;out.append(self.frame(3,r.copy()))
            if c.get('test')=='all':out.append(self.frame(3,dict(event='cycle_complete')))
        elif op=='confirm' and c.get('test') in self.results:
            r=self.results[c['test']];r['state']='passed' if c.get('confirm') else 'failed';r['code']='DEMO_OPERATOR_CONFIRMED';out.append(self.frame(3,r.copy()))
        return out
    def poll(self):
        now=time.monotonic();t=now-self.started
        if not self.rate or now-self.last_stream<1/self.rate:return []
        self.last_stream=now;stamp=int(t*1000);out=[]
        roll=math.radians(25*math.sin(t*.5));pitch=math.radians(15*math.sin(t*.35));yaw=t*.1
        # Body gravity consistent with Euler convention in orientation.py.
        accel=[-9.80665*math.sin(pitch),9.80665*math.cos(pitch)*math.sin(roll),9.80665*math.cos(pitch)*math.cos(roll)]
        # Euler derivatives -> body angular rates, so model follows a physical rotation.
        rd=math.radians(12.5*math.cos(t*.5));pd=math.radians(5.25*math.cos(t*.35));yd=.1
        gyro=[math.degrees(rd-yd*math.sin(pitch)),math.degrees(pd*math.cos(roll)+yd*math.sin(roll)*math.cos(pitch)),math.degrees(-pd*math.sin(roll)+yd*math.cos(roll)*math.cos(pitch))]
        for i,_ in enumerate(self.profile['imus']):out.append(self.frame(4,dict(sensor=f'imu{i}',sample_ms=stamp,sample_count=int(t*200),fresh=True,measurement_hz=199.8,configured_odr_hz=200,errors=0,saturated=0,accel_m_s2=accel,gyro_deg_s=gyro,temperature_c=29+i*.2,raw=[int(v*100) for v in accel+gyro]+[512],rotation='ROTATION_NONE')))
        for i,_ in enumerate(self.profile['barometers']):out.append(self.frame(4,dict(sensor=f'baro{i}',sample_ms=stamp,sample_count=int(t*32),fresh=True,measurement_hz=32,errors=0,pressure_pa=101325+20*math.sin(t*.2)+i,temperature_c=24+i*.1,relative_altitude_m=-1.66*math.sin(t*.2))))
        for name,value,scale,unit in [('voltage',12.1,self.profile['voltage_scale'],'V'),('current',0.1,83.333,'A'),('pressure',0,2,'V'),('rssi',0,1,'V')]:out.append(self.frame(4,dict(sensor='adc.'+name,sample_ms=stamp,raw=value/scale/3.3*65535,adc_voltage_v=value/scale,scale=scale,value=value,fresh=True,units=unit,measurement_hz=None)))
        return out
