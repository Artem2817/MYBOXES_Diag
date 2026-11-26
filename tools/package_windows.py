#!/usr/bin/env python3
"""Record a standalone Windows release and collect its dependency notices."""
from pathlib import Path
import argparse,hashlib,json,shutil,sysconfig
KIT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--dependencies',type=Path,default=Path(sysconfig.get_paths()['purelib']));p.add_argument('--native-demo-tested',action='store_true');a=p.parse_args()
 exe=KIT/'dist/windows-standalone/MyboxDiag-0.2.2-windows-x64.exe'
 if not exe.exists():raise SystemExit('Build the standalone Windows EXE first')
 notices=KIT/'pc/third-party-licenses';notices.mkdir(exist_ok=True)
 for package in a.dependencies.glob('*.dist-info'):
  for source in package.rglob('*'):
   if source.is_file() and any(word in source.name.lower() for word in ('license','copying','metadata')):
    target=notices/package.name/source.relative_to(package);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
 (KIT/'dist/windows-package.json').write_text(json.dumps(dict(file=exe.name,version='0.2.2',sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),standalone=True,native_windows_demo_tested=a.native_demo_tested,physical_board_tested=False),indent=2)+'\n')
 print(exe.name)
if __name__=='__main__':main()
