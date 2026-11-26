import json,random,struct,subprocess,sys,zlib
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pc'))
from mybox_diag.protocol import Parser,encode,MAGIC,HEADER

def test_fragmentation_corruption_noise_and_sequence():
    a=encode({'op':'ping','id':1},seq=0xffffffff);b=encode({'id':2,'ok':True},kind=2,seq=1)
    bad=bytearray(a);bad[-1]^=1;p=Parser();out=[]
    for byte in b'boot log\r\n'+bad+a+b:out+=p.feed(bytes([byte]),now=0)
    assert [f.body['id'] for f in out]==[1,2]
    assert p.errors==1 and p.missing==1

def test_stale_partial_frame_recovers_and_payload_is_bounded():
    p=Parser();p.feed(encode({'id':1})[:20],now=0)
    assert p.feed(encode({'id':2}),now=.251)[0].body['id']==2
    p.feed(MAGIC+b'\x01\x04\xff\xff'+bytes(8)+b'x'*9000,now=.3)
    assert len(p.buffer)<=4096+20
    assert p.feed(encode({'id':3}),now=.6)[0].body['id']==3

def test_invalid_json_never_reaches_ui():
    for raw in [b'{"x":NaN}',b'[]',b'{"x":1,"x":2}',b'\xff']:
        head=HEADER.pack(MAGIC,1,3,len(raw),1,0)+raw;p=Parser();assert not p.feed(head+struct.pack('<I',zlib.crc32(head)));assert p.errors==1

def test_random_fragmentation_roundtrip():
    random.seed(1234);packets=b''.join(encode({'id':i,'text':'Плата'},kind=4,seq=i) for i in range(100));p=Parser();out=[]
    while packets:
        n=random.randint(1,91);out+=p.feed(packets[:n],now=0);packets=packets[n:]
    assert len(out)==100 and p.errors==0 and p.missing==0

def test_firmware_wire_format_and_strict_command_parser(tmp_path):
    root=Path(__file__).resolve().parents[1]
    source=tmp_path/'wire.cpp'
    source.write_text(r'''
#include "protocol.h"
#include "command.h"
#include <assert.h>
#include <stdio.h>
int main() {
 Command c; assert(c.parse("{\"id\":123,\"op\":\"run\",\"test\":\"pwm1.scope\",\"confirm\":true,\"duration_ms\":1000}"));
 assert(c.id==123 && c.confirm && c.duration_ms==1000);
 const char *bad[]={"{\"id\":1,\"op\":\"ping\",}","{\"id\":1,\"id\":2,\"op\":\"run\"}","{\"id\":-1,\"op\":\"ping\"}","{\"id\":1,\"op\":\"ping\",\"confirm\":1}","{\"id\":4294967296,\"op\":\"ping\"}","{\"id\":0,\"op\":\"ping\"}"};
 for(auto s:bad){Command q;assert(!q.parse(s));}
 uint8_t out[4200];auto len=mbd::encode(out,2,42,1234,"{\"id\":123,\"ok\":true}");
 mbd::Parser p; bool complete=false;for(size_t i=0;i<len;i++){complete=p.feed(out[i],0);}assert(complete);assert(!strcmp(p.payload(),"{\"id\":123,\"ok\":true}"));
 p.consume(); for(size_t i=0;i<len/2;i++){p.feed(out[i],1);}for(size_t i=0;i<len;i++){complete=p.feed(out[i],252);}assert(complete);
 fwrite(out,1,len,stdout);
}
''')
    binary=tmp_path/'wire';subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(root/'firmware'),str(source),'-o',str(binary)],check=True)
    frames=Parser().feed(subprocess.check_output([binary]));assert len(frames)==1;assert frames[0].seq==42 and frames[0].time_ms==1234
