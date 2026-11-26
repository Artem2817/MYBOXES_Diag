#!/usr/bin/env python3
"""Verify both application-only and complete bootable diagnostic HEX images."""
from pathlib import Path
import argparse,hashlib,json,struct,zlib
from intelhex import read
VERSION='0.2.1'
def inspect(path):
    memory=read(path);full=path.name.endswith('-with-bootloader.hex');start=min(memory);end=max(memory)+1
    lower=0x08000000 if full else 0x08020000
    if start!=lower or any(not lower<=a<0x081c0000 for a in memory):raise ValueError('Write outside allowed firmware range')
    word=lambda a:int.from_bytes(bytes(memory.get(a+i,0) for i in range(4)),'little')
    def vector(address,limit):
        sp,reset=word(address),word(address+4)
        if not any(lo<sp<=hi for lo,hi in [(0x20000000,0x20020000),(0x24000000,0x24080000),(0x30000000,0x30048000),(0x38000000,0x38010000)]):raise ValueError('Invalid H743 stack')
        if not reset&1 or not address<=(reset&~1)<limit:raise ValueError('Invalid reset vector')
        return reset
    boot_reset=vector(0x08000000,0x08020000) if full else None
    reset=vector(0x08020000,end)
    image=bytes(memory.get(a,255) for a in range(0x08020000,end));sig=bytes.fromhex('40a2e4f164689106');offset=image.find(sig)
    if offset<0 or image.find(sig,offset+1)>=0:raise ValueError('Missing/ambiguous app descriptor')
    crc1,crc2,size,_=struct.unpack_from('<IIII',image,offset+8);crc=lambda b:(zlib.crc32(b,0xffffffff)^0xffffffff)&0xffffffff
    if size!=len(image) or crc1!=crc(image[:offset+8]) or crc2!=crc(image[offset+24:]):raise ValueError('Bootloader image CRC mismatch')
    board_id=struct.unpack_from('<H',image,offset+26)[0];expected=1480 if 'v2_vib' in path.name else 1479 if 'v2' in path.name else 1478
    if board_id!=expected:raise ValueError('Board ID mismatch')
    return dict(name=path.name,bootloader_included=full,start=hex(start),end_exclusive=hex(end),programmed_bytes=len(memory),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),reset=hex(reset),bootloader_reset=hex(boot_reset) if boot_reset else None,bootloader_descriptor_crc_valid=True,board_id=board_id)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);a=parser.parse_args();paths=sorted(a.directory.glob(f'MyboxDiag-{VERSION}-*.hex'))
    if len(paths)!=6:raise SystemExit('Expected three application and three complete HEX files')
    result=[inspect(p) for p in paths]
    for p in paths:
        if p.name.endswith('-with-bootloader.hex'):
            complete=read(p);app=read(p.with_name(p.name.replace('-with-bootloader','')))
            if {k:v for k,v in complete.items() if k>=0x08020000}!=app:raise ValueError('Combined application differs')
    (a.directory/'hex-validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
