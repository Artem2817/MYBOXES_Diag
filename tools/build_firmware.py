#!/usr/bin/env python3
"""Install a diagnostic overlay in a dedicated ArduPilot checkout; never flash."""
from pathlib import Path
import argparse, hashlib, json, os, re, shutil, subprocess, sys, fcntl
from intelhex import merge
KIT=Path(__file__).resolve().parents[1]
PINNED='046cafbceec1a30a202b2eefe64554e5ea54cf01'
BOARDS=['MyboxH743_mini','MyboxH743_mini_v2','MyboxH743_mini_v2_vib']
def main():
 p=argparse.ArgumentParser();p.add_argument('--checkout',type=Path,required=True);p.add_argument('--jobs',type=int,default=4);p.add_argument('--profile',choices=BOARDS,action='append');a=p.parse_args();checkout=a.checkout.resolve()
 if not (checkout/'.git').exists():raise SystemExit('Use a dedicated ArduPilot checkout with submodules; see README.')
 lock=(checkout/'.mybox-diagnostic-build.lock').open('w')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:raise SystemExit('Another diagnostic build owns this checkout; wait for it to finish.')
 head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=checkout,text=True).strip()
 if head!=PINNED:raise SystemExit(f'Expected platform commit {PINNED}, got {head}')
 thresholds=json.loads((KIT/'config/thresholds.json').read_text())['values']
 header='// Generated from config/thresholds.json; edit that file.\n#pragma once\nnamespace cfg {\n'
 for key,value in thresholds.items():
  header+='constexpr '+('float' if isinstance(value,float) else 'unsigned')+' '+key+' = '+str(value)+('f' if isinstance(value,float) else 'U')+';\n'
 header+='}\n';(KIT/'firmware/thresholds.h').write_text(header)
 inventory='#pragma once\n'
 for number,profile_name in enumerate(BOARDS):
  hw_profile=json.loads((KIT/'profiles'/f'{profile_name}.json').read_text())
  devices=hw_profile['imus']+hw_profile['barometers']+[{'id':x} for x in ['osd','sd','flash','adc','usb','uart1','uart2','uart3','uart4','uart5','can1','can2','rcin','led','safety']]
  if number:devices += [{'id':'buzzer'},{'id':'heater'}]
  inventory+=('#if' if number==0 else '#elif')+' MYBOX_DIAG_PROFILE == '+str(number)+'\nstatic const char *const EXPECTED_DEVICES_JSON=R"mbd('+json.dumps(devices,separators=(',',':'))+')mbd";\n'
 inventory+='#endif\n';(KIT/'firmware/inventory.h').write_text(inventory)
 dest=checkout/'libraries/AP_HAL/examples/MyboxDiag';dest.mkdir(parents=True,exist_ok=True)
 for f in (KIT/'firmware').iterdir():
  if f.is_file():shutil.copy2(f,dest/f.name)
 source_hash=hashlib.sha256(b''.join(f.read_bytes() for f in sorted((KIT/'firmware').glob('*')) if f.is_file())).hexdigest()[:16]
 env=os.environ.copy();env['PYTHONHASHSEED']='0';env['SOURCE_DATE_EPOCH']='1795132800';env['CCACHE_DIR']=str(checkout/'.diag-ccache')
 # Waf bundled in this pinned platform still uses the removed universal-newline flag.
 compat=checkout/'diag-python-compat';compat.mkdir(exist_ok=True)
 (compat/'sitecustomize.py').write_text("import builtins\n_orig=builtins.open\ndef compatible(file,mode='r',*args,**kw):\n return _orig(file,mode.replace('U',''),*args,**kw)\nbuiltins.open=compatible\n")
 env['PYTHONPATH']=str(compat)+os.pathsep+env.get('PYTHONPATH','')
 out=KIT/'dist/firmware';out.mkdir(parents=True,exist_ok=True)
 manifest=json.loads((out/'manifest.json').read_text()) if (out/'manifest.json').exists() else []
 for board in a.profile or BOARDS:
  profile=json.loads((KIT/'profiles'/f'{board}.json').read_text());name=['MBD_Mini','MBD_V2','MBD_V2Vib'][profile['index']];hw=checkout/'libraries/AP_HAL_ChibiOS/hwdef'/name;hw.mkdir(parents=True,exist_ok=True)
  source=KIT/'hardware'/board/'hwdef.dat'
  if hashlib.sha256(source.read_bytes()).hexdigest()!=profile['hwdef_sha256']:raise SystemExit('HWDEF snapshot does not match profile: '+board)
  text=source.read_text()
  text=text.replace('define HAL_OSD_TYPE_DEFAULT 1','define HAL_OSD_TYPE_DEFAULT 0')
  text=re.sub(r'^APJ_BOARD_ID .*$',f"APJ_BOARD_ID {profile['board_id']}",text,flags=re.M)
  # Keep bootloader and last two parameter sectors outside application image.
  text+='\n# Diagnostic-only additions; original HWDEF is untouched.\nFLASH_RESERVE_END_KB 256\ndefine HAL_USE_EMPTY_STORAGE 1\ndefine HAL_LOGGING_ENABLED 0\ndefine AP_BOOTLOADER_FLASHING_ENABLED 0\ndefine MYBOX_DIAG_PROFILE '+str(profile['index'])+'\n'
  text+='define MYBOX_DIAG_BUILD "'+source_hash+'"\n'
  # Force CAN silent for a bench application and heater off from reset.
  text=re.sub(r'(GPIO_CAN\d_SILENT OUTPUT PUSHPULL SPEED_LOW )LOW',r'\1HIGH',text)
  if board=='MyboxH743_mini':text+='\nPA15 DIAG_UNUSED_BUZZER OUTPUT LOW\n'
  else:text+='\n'
  (hw/'hwdef.dat').write_text(text)
  text=text.replace('PE3 SAFETY_IN INPUT PULLDOWN','PE3 SAFETY_IN INPUT PULLDOWN GPIO(92)').replace('PE2 LED_SAFETY OUTPUT','PE2 LED_SAFETY OUTPUT LOW GPIO(93)')
  (hw/'hwdef.dat').write_text(text)
  # default params aren't loaded; empty storage prevents persistent writes.
  with (out/(name+'.log')).open('w') as log:
   for cmd in [[sys.executable,'waf','configure','--board',name,'--disable-scripting','--consistent-build'],[sys.executable,'waf','--targets','examples/MyboxDiag','-j',str(a.jobs)]]:
    print(' '.join(cmd),flush=True);subprocess.run(cmd,cwd=checkout,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
  elf=checkout/'build'/name/'examples/MyboxDiag'
  tool=shutil.which('arm-none-eabi-objcopy')
  for extension,fmt in [('hex','ihex'),('bin','binary')]:
   target=out/f'MyboxDiag-0.2.1-{board}.{extension}';subprocess.run([tool,'--gap-fill','0xFF','-O',fmt,str(elf),str(target)],check=True)
  if (checkout/'build'/name/'bin/MyboxDiag.bin').read_bytes() != (out/f'MyboxDiag-0.2.1-{board}.bin').read_bytes():raise SystemExit('Patched ELF and generated BIN differ')
  shutil.copy2(elf,out/f'MyboxDiag-0.2.1-{board}.elf')
  bootname=name+'_BL';boothw=checkout/'libraries/AP_HAL_ChibiOS/hwdef'/bootname;boothw.mkdir(exist_ok=True)
  boottext=(KIT/'hardware'/board/'hwdef-bl.dat').read_text()
  boottext=re.sub(r'^APJ_BOARD_ID .*$',f"APJ_BOARD_ID {profile['board_id']}",boottext,flags=re.M)
  # PE4 active-low follows the established INAV Mini LED0_INVERTED target.
  boottext=boottext.replace('PE4 LED_BOOTLOADER OUTPUT LOW','PE4 LED_BOOTLOADER OUTPUT HIGH').replace('define HAL_LED_ON 1','define HAL_LED_ON 0')
  boottext+='\ndefine AP_CHECK_FIRMWARE_ENABLED 1\n'
  (boothw/'hwdef.dat').write_text(text);(boothw/'hwdef-bl.dat').write_text(boottext)
  with (out/(bootname+'.log')).open('w') as log:
   for cmd in [[sys.executable,'waf','configure','--board',bootname,'--bootloader','--consistent-build'],[sys.executable,'waf','bootloader','-j',str(a.jobs)]]:
    print(' '.join(cmd),flush=True);subprocess.run(cmd,cwd=checkout,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
  bootdir=out/'bootloaders';bootdir.mkdir(exist_ok=True)
  boothex=bootdir/f'MyboxBootloader-0.2.1-{board}.hex'
  bootelf=checkout/'build'/bootname/'bootloader/AP_Bootloader'
  subprocess.run([tool,'--gap-fill','0xFF','-O','ihex',str(bootelf),str(boothex)],check=True)
  full=out/f'MyboxDiag-0.2.1-{board}-with-bootloader.hex'
  merge(boothex,out/f'MyboxDiag-0.2.1-{board}.hex',full)
  manifest=[m for m in manifest if m['profile']!=board]
  manifest.append(dict(profile=board,version='0.2.1',full_file=full.name,full_sha256=hashlib.sha256(full.read_bytes()).hexdigest(),bootloader_file=str(boothex.relative_to(out)),build_id=source_hash,platform_commit=head,hardware_tested=False,application_address='0x08020000',end_exclusive='0x081c0000',hwdef_sha256=profile['hwdef_sha256']))
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 (out/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(f.read_bytes()).hexdigest()+'  '+f.name+'\n' for f in sorted(out.glob('MyboxDiag-0.2.1-*'))))
if __name__=='__main__':main()
