"""Serial I/O lives in a worker; commands and timeout state never block the UI."""
import itertools,queue,time
from PySide6.QtCore import QThread,Signal
import serial
from .protocol import Parser,encode
from .simulator import DemoPeer
class Connection(QThread):
    frames=Signal(object);status=Signal(str);stats=Signal(object);fault=Signal(str)
    def __init__(self,port=None,demo=False,profile='MyboxH743_mini_v2_vib',rate=20):
        super().__init__();self.port=port;self.demo=demo;self.profile=profile;self.rate=rate;self.commands=queue.Queue(128);self.running=True;self.ids=itertools.count(1)
    def request(self,op,**kw):
        body={'id':next(self.ids),'op':op,**kw}
        try:self.commands.put_nowait(body)
        except queue.Full:self.fault.emit('Очередь команд заполнена')
        return body['id']
    def stop(self):self.running=False;self.requestInterruption()
    def run(self):
        parser=Parser();device=None;peer=DemoPeer(self.profile) if self.demo else None;pending={};sequence=0;last_ping=0;last_stats=0;last_valid=time.monotonic();handshake=False;rx_frames=0
        try:
            self.status.emit('Подключение…')
            if not self.demo:device=serial.Serial(self.port,115200,timeout=.02,write_timeout=.1,exclusive=None)
            self.request('info');self.request('list');self.request('results');self.request('stream',rate=self.rate)
            while self.running and not self.isInterruptionRequested():
                now=time.monotonic()
                if now-last_ping>.3:self.request('ping');last_ping=now
                batch=[]
                for _ in range(16):
                    try:c=self.commands.get_nowait()
                    except queue.Empty:break
                    sequence+=1;pending[c['id']]=(now,c['op'])
                    if peer:batch.extend(peer.request(c))
                    else:
                        packet=encode(c,seq=sequence,time_ms=int(now*1000))
                        if device.write(packet)!=len(packet):raise serial.SerialTimeoutException('Неполная запись USB')
                if peer:batch.extend(peer.poll());self.msleep(10)
                else:batch.extend(parser.feed(device.read(min(max(device.in_waiting,1),65536))))
                for f in batch:
                    rx_frames+=1;last_valid=now
                    if f.kind==2:
                        pending.pop(f.body.get('id'),None)
                        if not f.body.get('ok',False):self.fault.emit('Устройство: '+f.body.get('code','UNKNOWN'))
                        if f.body.get('op')=='info':
                            if f.body.get('protocol')!=1:raise RuntimeError('Несовместимая версия протокола')
                            if not handshake:handshake=True;self.status.emit('ДЕМОНСТРАЦИЯ' if self.demo else 'Подключено')
                if batch:self.frames.emit(batch)
                expired=[i for i,(start,op) in pending.items() if now-start>2]
                for i in expired:
                    _,op=pending.pop(i)
                    self.fault.emit('Тайм-аут ответа: '+op)
                if now-last_valid>3:raise RuntimeError('Нет корректных сообщений более 3 секунд')
                if now-last_stats>1:self.stats.emit(dict(parser_errors=parser.errors,missing_frames=parser.missing,received_frames=rx_frames,pending=len(pending)));last_stats=now
        except (serial.SerialException,OSError,RuntimeError,ValueError) as error:self.fault.emit(str(error))
        finally:
            if device:
                try:device.write(encode({'id':next(self.ids),'op':'stop'},seq=sequence+1))
                except (OSError,serial.SerialException):pass
                device.close()
            self.status.emit('Отключено')
