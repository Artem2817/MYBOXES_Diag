@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name MyboxDiag-0.2.2-windows-x64 --distpath ..\dist\windows-standalone --workpath ..\.windows-build\work --specpath ..\.windows-build --add-data "mybox_diag\profiles;mybox_diag\profiles" --add-data "mybox_diag\test_catalog.json;mybox_diag" run.py
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe ..\tools\package_windows.py
