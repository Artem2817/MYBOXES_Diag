#!/usr/bin/env python3
"""Run the real GUI and USB worker, recording an automatic physical board session (including an SD scratch file)."""
import argparse,json,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pc'))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from mybox_diag.app import Window

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',required=True);parser.add_argument('--seconds',type=int,default=60);parser.add_argument('--output',required=True);args=parser.parse_args()
    application=QApplication([]);window=Window(SimpleNamespace(output=args.output,demo=False,smoke_demo=False));window.show();window._connect(args.port)
    def finish():
        session=window.session
        summary=dict(board=session.board,telemetry_packets=session.telemetry_count,transport=session.transport,events=[e for e in session.events if e.get('origin')=='pc'])
        Path(args.output,'physical-usb-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(summary,ensure_ascii=True),flush=True);window.close()
    QTimer.singleShot(args.seconds*1000,finish)
    return application.exec()
if __name__=='__main__':raise SystemExit(main())
