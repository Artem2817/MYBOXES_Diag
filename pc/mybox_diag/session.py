from datetime import datetime,timezone
from pathlib import Path
import csv,html,json,uuid
from .automatic import CATALOG
STATES={'passed':'Пройден','failed':'Ошибка','warning':'Предупреждение','not_tested':'Не проверен','needs_action':'Требуется оборудование / действие','not_applicable':'Не применимо','running':'Выполняется'}
class Session:
    def __init__(self,demo=False):
        self.id=str(uuid.uuid4());self.started=datetime.now(timezone.utc).isoformat();self.demo=demo
        self.board={};self.tests={};self.results={};self.catalog_complete=False;self.catalog_seen=set();self.events=[];self.latest={};self.telemetry_count=0;self.transport={}
        self._csv=None;self._writer=None;self._journal=None;self.directory=None
    def start_recording(self,directory):
        if self._csv:return
        self.directory=Path(directory)/self.id;self.directory.mkdir(parents=True,exist_ok=False)
        self._csv=(self.directory/'telemetry.csv').open('w',newline='',encoding='utf-8-sig')
        self._writer=csv.writer(self._csv);self._writer.writerow(['session_id','demo','received_utc','frame_seq','board_time_ms','sensor','sample_ms','sample_count','channel','value','unit'])
        self._journal=(self.directory/'events.jsonl').open('w',encoding='utf-8')
    def ingest(self,frame):
        b=frame.body;stamp=datetime.now(timezone.utc).isoformat()
        if frame.kind==2 and b.get('op')=='info':self.board=dict(b)
        elif frame.kind==3:
            if b.get('event')=='list_complete':self.catalog_complete=True
            if b.get('event')=='test':
                self.catalog_seen.add(b['test'])
                if b['test'] not in CATALOG:return
                self.tests[b['test']]={**b,'automatic':True}
            elif b.get('event')=='result':
                if b['test'] not in CATALOG:return
                self.results[b['test']]=dict(b)
            else:
                self.events.append({'received_utc':stamp,**b})
                if len(self.events)>10000:del self.events[:1000]
        elif frame.kind==4:
            self.latest[b['sensor']]=dict(b);self.telemetry_count+=1
            if self._writer:
                units={'accel_m_s2':'m/s2','gyro_deg_s':'deg/s','temperature_c':'C','pressure_pa':'Pa','relative_altitude_m':'m','adc_voltage_v':'V','value':b.get('units',''),'measurement_hz':'Hz','raw':'counts'}
                for k,unit in units.items():
                    if k not in b:continue
                    values=b[k] if isinstance(b[k],list) else [b[k]]
                    for i,value in enumerate(values):self._writer.writerow([self.id,self.demo,stamp,frame.seq,frame.time_ms,b['sensor'],b.get('sample_ms'),b.get('sample_count'),k+(f'.{i}' if len(values)>1 else ''),value,unit])
        if self._journal and frame.kind!=4:
            self._journal.write(json.dumps({'utc':stamp,'seq':frame.seq,'board_time_ms':frame.time_ms,'body':b},ensure_ascii=False)+'\n');self._journal.flush()
    def note(self,event,**fields):
        entry={'received_utc':datetime.now(timezone.utc).isoformat(),'origin':'pc','event':event,**fields};self.events.append(entry)
        if self._journal:self._journal.write(json.dumps(entry,ensure_ascii=False)+'\n');self._journal.flush()
    @property
    def catalog_valid(self):
        expected=self.board.get('test_count');received=len(self.catalog_seen) if self.catalog_seen else len(self.tests)
        return self.catalog_complete and (not isinstance(expected,int) or received==expected)
    def conclusion(self):
        applicable={k:v for k,v in self.tests.items() if v.get('applicable',True)}
        if any(self.results.get(k,{}).get('state')=='failed' for k in applicable):return 'Обнаружены неисправности'
        if not self.catalog_valid:return 'Неполная проверка'
        if applicable and all(self.results.get(k,{}).get('state')=='passed' for k in applicable):return 'Автоматические проверки пройдены'
        return 'Неполная проверка'
    def report(self):
        return dict(schema=2,scope='automatic_checks_only',session_id=self.id,started_utc=self.started,exported_utc=datetime.now(timezone.utc).isoformat(),demo=self.demo,evidence='DEMONSTRATION_ONLY' if self.demo else 'device_session',board=self.board,inventory=self._inventory(),tests=self.tests,results=self.results,conclusion=self.conclusion(),events=self.events,latest_telemetry=self.latest,telemetry_packets=self.telemetry_count,transport=self.transport)
    def _inventory(self):
        p=Path(__file__).parent/'profiles'/f"{self.board.get('profile','unknown')}.json"
        return json.loads(p.read_text(encoding='utf-8')) if p.is_file() else {'error':'Unknown profile; inventory unavailable'}
    def export(self,directory):
        d=Path(directory);d.mkdir(parents=True,exist_ok=True);report=self.report()
        (d/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        esc=lambda s:html.escape(str(s))
        rows=[]
        for key,definition in self.tests.items():
            r=self.results.get(key,{'state':'not_tested','code':'NOT_RUN'})
            rows.append('<tr>'+''.join(f'<td>{esc(v)}</td>' for v in [key,STATES.get(r.get('state'),r.get('state')),r.get('code',''),r.get('expected',''),r.get('actual',''),r.get('detail',''),r.get('duration_ms','')])+ '</tr>')
        title=('ДЕМОНСТРАЦИЯ — не диагностика физической платы' if self.demo else 'Диагностика платы Mybox')
        content=f'''<!doctype html><html lang="ru"><meta charset="utf-8"><title>Отчёт MYBOX</title><style>body{{font:16px system-ui;margin:2rem;color:#17243a}}table{{border-collapse:collapse;width:100%}}th,td{{padding:.6rem;border:1px solid #ccd;text-align:left}}pre{{white-space:pre-wrap}}.demo{{color:#a30}}</style><h1 class="demo">{esc(title)}</h1><p>{esc(self.conclusion())}</p><p>Сеанс {esc(self.id)} · {esc(self.started)}</p><h2>Плата и прошивка</h2><pre>{esc(json.dumps(self.board,ensure_ascii=False,indent=2))}</pre><p>Ревизия из сборки; аппаратное определение ревизии отсутствует. Ориентация из аппаратного профиля.</p><h2>Проверки</h2><table><thead><tr><th>Тест</th><th>Статус</th><th>Код</th><th>Ожидание</th><th>Факт</th><th>Пояснение</th><th>мс</th></tr></thead><tbody>{''.join(rows)}</tbody></table><p>Итог относится только к автоматическим проверкам из таблицы.</p><p>Полный инвентарь, события и телеметрия: report.json; запись потока: telemetry.csv.</p></html>'''
        (d/'report.html').write_text(content,encoding='utf-8');return d/'report.html'
    def close(self):
        if self._csv:self._csv.flush();self._csv.close();self._csv=None;self._writer=None
        if self._journal:self._journal.close();self._journal=None
        if self.directory:self.export(self.directory)
