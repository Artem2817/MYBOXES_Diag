from types import SimpleNamespace as NS
from mybox_diag.ports import capture_port,find_port

def port(device='COM42',serial='BOARD-A',description='ArduPilot MAVLink'):
    return NS(device=device,vid=0x1209,pid=0x5740,serial_number=serial,description=description)

def test_usb_identity_survives_com_change_and_excludes_slcan():
    identity=capture_port('COM42',[port()])
    assert find_port(identity,[port('COM44'),port('COM45',description='ArduPilot SLCAN')])=='COM44'
    assert find_port(identity,[]) is None
    assert find_port(identity,[port('COM42',serial='BOARD-B')]) is None
    assert find_port(identity,[port('COM44'),port('COM46')]) is None
    assert find_port(identity,[port('COM43',description='ArduPilot SLCAN')]) is None

def test_no_usb_serial_never_guesses_another_port():
    identity=capture_port('COM42',[port(serial=None)])
    assert find_port(identity,[port('COM44',serial=None)]) is None
    assert find_port(identity,[port(serial=None)])=='COM42'

def test_window_waits_then_reconnects_without_losing_recording(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QObject,Signal
    from mybox_diag import app as gui
    application=QApplication.instance() or QApplication([])
    class Worker(QObject):
        frames=Signal(object);status=Signal(str);stats=Signal(object);fault=Signal(str);finished=Signal()
        def __init__(self,**kw):super().__init__();self.options=kw
        def start(self):pass
        def isRunning(self):return False
        def stop(self):pass
        def wait(self,ms):return True
    available=[port(),port('COM43',description='ArduPilot SLCAN')]
    monkeypatch.setattr(gui.list_ports,'comports',lambda:available)
    monkeypatch.setattr(gui,'Connection',Worker)
    w=gui.Window(NS(output=str(tmp_path),demo=False,smoke_demo=False))
    try:
        assert w.ports.count()==1 and not w.full.isEnabled()
        w.rate.setValue(7);w._connect('COM42');session=w.session;first=w.worker
        first.finished.emit();assert session._journal is not None
        available.clear();w._retry();assert w.worker is first
        assert 'Ожидание платы' in w.banner.text()
        session.catalog_complete=True;session.results['old']={'state':'passed'}
        available.append(port('COM44'));w._retry()
        assert w.worker.options['port']=='COM44' and w.worker.options['rate']==7
        assert w.session is session and session._journal is not None
        assert not session.catalog_complete and not session.results
        w.disconnect();assert session._journal is None
    finally:w.close();application.processEvents()
