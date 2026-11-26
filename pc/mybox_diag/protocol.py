"""MBD/1: bounded, CRC-protected JSON frames shared with firmware/protocol.h."""
from dataclasses import dataclass
import json,struct,time,zlib,math
MAGIC=b'MBD1';VERSION=1;HEADER=struct.Struct('<4sBBHII');MAX_PAYLOAD=4096
@dataclass(frozen=True)
class Frame:
    kind:int
    seq:int
    time_ms:int
    body:dict

def encode(body:dict,kind:int=1,seq:int=0,time_ms:int=0)->bytes:
    data=json.dumps(body,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')
    if len(data)>MAX_PAYLOAD:raise ValueError('payload exceeds 4096 bytes')
    packet=HEADER.pack(MAGIC,VERSION,kind,len(data),seq&0xffffffff,time_ms&0xffffffff)+data
    return packet+struct.pack('<I',zlib.crc32(packet))

def _reject_constant(value):raise ValueError(f'Nonfinite JSON {value}')
def _unique_pairs(pairs):
    result={}
    for k,v in pairs:
        if k in result:raise ValueError('Duplicate JSON key')
        result[k]=v
    return result
class Parser:
    def __init__(self):
        self.buffer=bytearray();self.last_input=None;self.errors=0;self.missing=0;self.last_seq=None
    def reset(self):
        self.buffer.clear();self.last_input=None;self.last_seq=None;self.errors=0;self.missing=0
    def feed(self,data:bytes,now:float|None=None)->list[Frame]:
        now=time.monotonic() if now is None else now
        if self.buffer and self.last_input is not None and now-self.last_input>0.250:
            self.buffer.clear();self.errors+=1
        if data:self.last_input=now;self.buffer.extend(data)
        frames=[]
        while True:
            start=self.buffer.find(MAGIC)
            if start<0:
                if len(self.buffer)>3:del self.buffer[:-3]
                break
            if start:del self.buffer[:start]
            if len(self.buffer)<HEADER.size:break
            _,version,kind,length,seq,stamp=HEADER.unpack_from(self.buffer)
            if version!=VERSION or length>MAX_PAYLOAD or kind not in (1,2,3,4):
                del self.buffer[0];self.errors+=1;continue
            total=HEADER.size+length+4
            if len(self.buffer)<total:break
            packet=bytes(self.buffer[:total])
            if zlib.crc32(packet[:-4])!=struct.unpack_from('<I',packet,total-4)[0]:
                del self.buffer[0];self.errors+=1;continue
            del self.buffer[:total]
            try:
                body=json.loads(packet[HEADER.size:-4].decode('utf-8'),parse_constant=_reject_constant,object_pairs_hook=_unique_pairs)
                if not isinstance(body,dict):raise ValueError('JSON object required')
            except (ValueError,UnicodeError,RecursionError):self.errors+=1;continue
            if self.last_seq is not None:
                delta=(seq-self.last_seq)&0xffffffff
                if 1<delta<0x80000000:self.missing+=delta-1
            self.last_seq=seq
            frames.append(Frame(kind,seq,stamp,body))
        return frames
