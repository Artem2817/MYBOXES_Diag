from mybox_diag.automatic import AutoRunner,CATALOG
from mybox_diag.protocol import Frame
from mybox_diag.session import Session

def reply(id,ok=True,**fields):return Frame(2,id,0,dict(id=id,ok=ok,**fields))
def result(key,state='passed'):return Frame(3,100,0,dict(event='result',test=key,state=state))

def test_auto_sequence_waits_for_ack_and_result_and_never_drives_outputs():
    sent=[];failed=[]
    def send(op,**kw):sent.append((op,kw));return len(sent)
    runner=AutoRunner(send,lambda *args:failed.append(args))
    runner.start(['pwm1.scope','sd.write','imu0.id']);assert sent==[('stop',{})]
    runner.handle(reply(1));assert sent[-1]==('run',dict(test='sd.write',confirm=False,duration_ms=1000))
    runner.handle(result('sd.write'));assert len(sent)==2  # result may arrive before its ACK
    runner.handle(reply(2));assert sent[-1][1]['test']=='imu0.id'
    runner.handle(reply(3));runner.handle(result('imu0.id','failed'))
    assert not runner.busy and not failed and len(sent)==3

def test_auto_rejection_timeout_and_stop_cannot_leave_a_running_queue():
    now=[0];sent=[];failed=[]
    def send(op,**kw):sent.append((op,kw));return len(sent)
    runner=AutoRunner(send,lambda *args:failed.append(args),clock=lambda:now[0])
    runner.start(['sd.write']);now[0]=4;runner.tick()
    assert not runner.busy and failed==[(None,'AUTO_TIMEOUT')] and sent[-1][0]=='stop'
    runner.start(['sd.write']);runner.handle(reply(len(sent)));id=len(sent)
    runner.handle(reply(id,False,code='BUSY'));assert failed[-1]==('sd.write','BUSY') and not runner.busy
    runner.start(['imu0.id']);runner.stop();count=len(sent);runner.handle(reply(count-1));runner.handle(result('imu0.id'));assert len(sent)==count

def test_legacy_firmware_catalog_is_complete_but_manual_checks_are_absent_from_report(tmp_path):
    session=Session();legacy=[*CATALOG,'pwm1.scope','led.visual'];session.board={'test_count':len(legacy)}
    for i,key in enumerate(legacy):
        session.ingest(Frame(3,i,0,dict(event='test',test=key,applicable=True,automatic=key!='sd.write')))
        session.ingest(result(key))
    session.ingest(Frame(3,100,0,dict(event='list_complete')))
    assert session.catalog_valid and set(session.tests)==set(CATALOG) and set(session.results)==set(CATALOG)
    assert session.conclusion()=='Автоматические проверки пройдены'
    report=session.report();assert report['scope']=='automatic_checks_only' and 'operator_confirmations' not in report
    assert 'pwm1.scope' not in session.export(tmp_path).read_text()
    assert 'led.visual' not in session.export(tmp_path).read_text()
