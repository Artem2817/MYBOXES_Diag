#!/usr/bin/env python3
"""Record real USB diagnostics without starting active output tests."""
from pathlib import Path
import argparse,json,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pc'))
from mybox_diag.protocol import Parser,encode
import serial
from serial.tools import list_ports
p=argparse.ArgumentParser();p.add_argument('--port',default='COM42');p.add_argument('--seconds',type=float,default=45);p.add_argument('--rate',type=int,default=20);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
a.output.parent.mkdir(parents=True,exist_ok=True);parser=Parser();start=time.monotonic();seq=0;request=0;counts={};last_ping=0;last_info=0;last_print=0;last_frame=start
log=a.output.open('w',encoding='utf-8');dev=None
def note(kind,**fields):log.write(json.dumps(dict(host_s=round(time.monotonic()-start,3),kind=kind,**fields),ensure_ascii=False)+'\n');log.flush()
def send(op,**fields):
 global seq,request
 seq+=1;request+=1;dev.write(encode(dict(id=request,op=op,**fields),seq=seq))
try:
 dev=serial.Serial(a.port,115200,timeout=.03,write_timeout=.2)
 for op,kw in [('info',{}),('list',{}),('results',{}),('stream',{'rate':a.rate})]:send(op,**kw)
 while time.monotonic()-start<a.seconds:
  now=time.monotonic()
  if now-last_ping>.25:send('ping');last_ping=now
  if now-last_info>2:send('info');last_info=now
  data=dev.read(min(max(dev.in_waiting,1),65536))
  for f in parser.feed(data):
   last_frame=now;note('frame',seq=f.seq,board_ms=f.time_ms,type=f.kind,body=f.body)
   if f.kind==4:counts[f.body.get('sensor','?')]=counts.get(f.body.get('sensor','?'),0)+1
   if f.body.get('op')=='info':print(json.dumps(dict(info=f.body,host_s=round(now-start,1)),ensure_ascii=True),flush=True)
   if f.body.get('event')=='result' and f.body.get('state') in ('failed','warning'):print(json.dumps(f.body,ensure_ascii=True),flush=True)
  if now-last_print>5:print(json.dumps(dict(host_s=round(now-start,1),counts=counts,parser_errors=parser.errors,missing=parser.missing,last_frame_age_s=round(now-last_frame,2))),flush=True);last_print=now
except Exception as error:
 note('error',error=str(error));print(type(error).__name__,str(error),flush=True)
 print(json.dumps([dict(port=p.device,vid=p.vid,pid=p.pid,serial=p.serial_number,description=p.description) for p in list_ports.comports()],ensure_ascii=True),flush=True)
finally:
 if dev:
  try:send('stream',rate=0);send('stop')
  except Exception:pass
  dev.close()
 note('summary',counts=counts,parser_errors=parser.errors,missing=parser.missing);log.close()
