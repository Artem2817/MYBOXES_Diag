"""Exercise the actual serial worker against an OS pseudo-terminal, including unplug."""
import os,pty,sys,threading,time
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pc'))
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from mybox_diag.transport import Connection
from mybox_diag.protocol import Parser,encode

def test_real_worker_handshake_bad_crc_and_disconnect():
    app=QApplication.instance() or QApplication([]);master,slave=pty.openpty();name=os.ttyname(slave);stop=threading.Event();states=[];frames=[];faults=[]
    def device():
        parser=Parser();seq=0
        while not stop.is_set():
            try:raw=os.read(master,4096)
            except OSError:return
            for f in parser.feed(raw):
                seq+=1;b=f.body
                response={'id':b['id'],'ok':True}
                if b['op']=='info':response.update(op='info',protocol=1,profile='MyboxH743_mini',uid='PTY-TEST',demo=False)
                packet=encode(response,kind=2,seq=seq)
                try:
                    if seq==1:bad=bytearray(packet);bad[-1]^=1;os.write(master,b'noise'+bad)
                    # Split wire frames exactly as USB may do.
                    os.write(master,packet[:7]);os.write(master,packet[7:])
                except OSError:return
    peer=threading.Thread(target=device,daemon=True);peer.start();worker=Connection(name);worker.status.connect(states.append);worker.frames.connect(frames.extend);worker.fault.connect(faults.append);worker.start()
    deadline=time.monotonic()+3
    while 'Подключено' not in states and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    assert 'Подключено' in states and any(f.body.get('uid')=='PTY-TEST' for f in frames)
    stop.set();os.close(master);os.close(slave)
    deadline=time.monotonic()+4
    while worker.isRunning() and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    if worker.isRunning():worker.stop();worker.wait(1000)
    app.processEvents();assert not worker.isRunning() and faults
