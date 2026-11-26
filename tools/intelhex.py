"""Small strict Intel HEX reader/writer for isolated bootloader/application images."""
from pathlib import Path

def read(path):
    memory={};upper=0;eof=False
    for line in Path(path).read_text().splitlines():
        if eof or not line.startswith(':'):raise ValueError('Invalid HEX record order')
        b=bytes.fromhex(line[1:]);n=b[0];address=int.from_bytes(b[1:3],'big');kind=b[3]
        if len(b)!=n+5 or sum(b)&255:raise ValueError('HEX checksum or length')
        if kind==0:
            for i,v in enumerate(b[4:-1]):
                a=upper+address+i
                if a in memory:raise ValueError('Overlapping HEX addresses')
                memory[a]=v
        elif kind==4:upper=int.from_bytes(b[4:-1],'big')<<16
        elif kind==1:eof=True
        elif kind not in (3,5):raise ValueError('Unsupported HEX record')
    if not eof or not memory:raise ValueError('Unterminated/empty HEX')
    return memory

def write(path,memory):
    lines=[];current=None;addresses=sorted(memory);i=0
    def record(kind,offset,data):
        b=bytes([len(data)])+offset.to_bytes(2,'big')+bytes([kind])+bytes(data);return ':'+(b+bytes([(-sum(b))&255])).hex().upper()
    while i<len(addresses):
        start=addresses[i];high=start>>16
        if high!=current:lines.append(record(4,0,high.to_bytes(2,'big')));current=high
        data=[memory[start]];i+=1
        while i<len(addresses) and addresses[i]==start+len(data) and len(data)<16 and addresses[i]>>16==high:data.append(memory[addresses[i]]);i+=1
        lines.append(record(0,start&65535,data))
    lines.append(':00000001FF');Path(path).write_text('\n'.join(lines)+'\n')

def merge(boot,application,target):
    b=read(boot);a=read(application)
    if min(b)!=0x08000000 or max(b)>=0x08020000:raise ValueError('Bootloader address range')
    if min(a)!=0x08020000 or max(a)>=0x081c0000:raise ValueError('Application address range')
    if b.keys()&a.keys():raise ValueError('Bootloader/application overlap')
    write(target,{**b,**a})
