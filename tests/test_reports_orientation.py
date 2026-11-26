import math,sys,json
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pc'))
from mybox_diag.orientation import Orientation,euler
from mybox_diag.session import Session
from mybox_diag.protocol import Frame
from mybox_diag.simulator import DemoPeer

def test_relative_yaw_zero_and_wrap():
    o=Orientation()
    for i in range(201):o.update(dict(fresh=True,sample_ms=(0xfffffc00+i*5)&0xffffffff,accel_m_s2=[0,0,9.80665],gyro_deg_s=[0,0,90]))
    assert abs(euler(o.q)[2]-90)<.1
    o.reset_zero();assert max(map(abs,euler(o.display_q)))<1e-6

def test_stale_samples_and_nonfinite_do_not_rotate():
    o=Orientation();before=o.q.copy();o.update(dict(fresh=False,sample_ms=0));assert np.array_equal(o.q,before)
    o.update(dict(fresh=True,sample_ms=1,accel_m_s2=[float('nan'),0,0],gyro_deg_s=[0,0,0]));assert np.array_equal(o.q,before)

def test_demo_reports_cannot_claim_real_hardware(tmp_path):
    s=Session(demo=True);s.start_recording(tmp_path/'sessions');peer=DemoPeer()
    for c in [dict(id=1,op='info'),dict(id=2,op='list'),dict(id=3,op='run',test='all')]:
        for frame in peer.request(c):s.ingest(frame)
    for frame in peer.poll():s.ingest(frame)
    report=s.export(tmp_path/'export');body=report.read_text();s.close()
    assert 'ДЕМОНСТРАЦИЯ' in body and 'Автоматические проверки пройдены' in body
    raw=json.loads((report.parent/'report.json').read_text());assert raw['demo'] and raw['evidence']=='DEMONSTRATION_ONLY'
    assert raw['board']['uid']=='DEMO-NO-PHYSICAL-BOARD'
    assert (s.directory/'telemetry.csv').stat().st_size>100
    assert 'pins' in raw['inventory']

def test_unrun_and_warning_tests_prevent_full_success():
    s=Session();s.catalog_complete=True;s.tests={'a':{'applicable':True},'b':{'applicable':True}}
    s.results={'a':{'state':'passed'}};assert s.conclusion()=='Неполная проверка'
    s.results['b']={'state':'warning'};assert s.conclusion()=='Неполная проверка'
    s.results['b']={'state':'failed'};assert s.conclusion()=='Обнаружены неисправности'
    s.results['b']={'state':'passed'};assert s.conclusion()=='Автоматические проверки пройдены'

def test_html_escapes_device_strings(tmp_path):
    s=Session();s.board={'uid':'<script>bad</script>'};text=s.export(tmp_path).read_text();assert '<script>bad</script>' not in text;assert '&lt;script&gt;' in text


def test_missing_catalog_entries_cannot_be_successful():
    s=Session();s.board={'test_count':2};s.tests={'a':{'applicable':True}};s.results={'a':{'state':'passed'}}
    assert s.conclusion()=='Неполная проверка'
    s.catalog_complete=True;assert s.conclusion()=='Неполная проверка'
    s.tests['b']={'applicable':True};assert s.conclusion()=='Неполная проверка'
    s.results['b']={'state':'passed'};assert s.conclusion()=='Автоматические проверки пройдены'
