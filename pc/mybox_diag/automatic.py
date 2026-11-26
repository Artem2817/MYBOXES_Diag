"""Only checks that complete without jumpers, instruments, or operator confirmation."""
import json,time
from collections import deque
from pathlib import Path

CATALOG={test['test']:test for test in json.loads((Path(__file__).parent/'test_catalog.json').read_text(encoding='utf-8'))}

class AutoRunner:
    """Wait for stop/run acknowledgements and each terminal result before advancing."""
    def __init__(self,send,failed,clock=time.monotonic):
        self.send=send;self.failed=failed;self.clock=clock;self.cancel()
    def cancel(self):
        self.busy=False;self.current=None;self.pending=None;self.queue=deque();self.terminal=False;self.deadline=0
    def start(self,keys):
        if self.busy:return
        self.queue=deque(key for key in keys if key in CATALOG)
        if not self.queue:return
        self.busy=True;self.current=None;self.terminal=False;self.pending=self.send('stop');self.deadline=self.clock()+3
    def stop(self):
        self.cancel();self.send('stop')
    def _next(self):
        if not self.queue:self.cancel();return
        self.current=self.queue.popleft();self.terminal=False
        self.pending=self.send('run',test=self.current,confirm=False,duration_ms=1000);self.deadline=self.clock()+9
    def handle(self,frame):
        if not self.busy:return
        body=frame.body
        if frame.kind==2 and body.get('id')==self.pending:
            self.pending=None
            if not body.get('ok',False):self._fail(body.get('code','COMMAND_REJECTED'));return
            if self.current is None or self.terminal:self._next()
        elif frame.kind==3 and body.get('event')=='result' and body.get('test')==self.current and body.get('state') not in ('running','not_tested'):
            self.terminal=True
            if self.pending is None:self._next()
    def tick(self):
        if self.busy and self.clock()>self.deadline:self._fail('AUTO_TIMEOUT')
    def _fail(self,code):
        key=self.current;self.cancel();self.send('stop');self.failed(key,code)
