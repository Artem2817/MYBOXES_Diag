#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,shutil,zipfile
KIT=Path(__file__).resolve().parents[1]
def main():
 site=KIT/'site-source';dest=site/'diagnostics'
 if dest.exists():shutil.rmtree(dest)
 dest.mkdir()
 rows=[]
 for m in sorted(json.loads((KIT/'dist/firmware/manifest.json').read_text()),key=lambda m:m['profile']):
  name=m['full_file'];f=KIT/'dist/firmware'/name;shutil.copy2(f,dest/name)
  rows.append({**m,'file':'diagnostics/'+name,'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'size':f.stat().st_size})
 if len(rows)!=3:raise SystemExit('Package all three profiles before publication')
 exe=KIT/'dist/windows-standalone/MyboxDiag-0.2.2-windows-x64.exe'
 if not exe.exists():raise SystemExit('Build the standalone EXE first')
 shutil.copy2(exe,dest/exe.name)
 manifest=dict(schema=2,version='0.2.2',channel='bench',physical_validation=False,bootloader_included=True,profiles=rows,windows_exe='diagnostics/'+exe.name,windows_sha256=hashlib.sha256(exe.read_bytes()).hexdigest())
 (site/'diagnostic-index.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
 names={'MyboxH743_mini':('Mini','Старая ревизия'),'MyboxH743_mini_v2':('Mini V2','Без виброразвязки'),'MyboxH743_mini_v2_vib':('Mini V2 Vib','С виброразвязкой')}
 cards=[]
 for r in rows:
  title,subtitle=names[r['profile']]
  cards.append(f'<article><h3>{title}</h3><p>{subtitle}</p><a href="{r["file"]}" download>Скачать HEX с загрузчиком</a></article>')
 page='<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Проверка MYBOX</title><link rel="stylesheet" href="styles.css?v=4"></head><body><header class="shell diagnostic-simple"><nav class="nav"><strong>MYBOXES</strong><a class="repo-link" href="./">ArduPilot / INAV</a></nav><h1>Проверка MYBOX</h1><p>Скачать. Прошить. Проверить.</p></header><main class="shell diagnostic-simple"><h2>1. Скачайте прошивку своей платы</h2><p>Все HEX ниже уже содержат нужный загрузчик и диагностическое приложение.</p><div class="diagnostic-list">'+''.join(cards)+'</div><h2>2. Прошейте плату</h2><p>Откройте HEX в STM32CubeProgrammer и загрузите через DFU. После записи снимите BOOT0 / отпустите BOOT и перезапустите плату. При запуске зелёный LED должен мигать.</p><h2>3. Запустите приложение</h2><a class="diag-exe" href="diagnostics/MyboxDiag-0.2.2-windows-x64.exe" download>Скачать EXE для Windows</a><p>Слева — положение платы. Справа — шесть блоков автоматической проверки. Подробности открываются в постоянной панели. Графики IMU, барометров и питания — в меню «•••».</p><p>Один файл, без установки Python. Подключите плату по USB и выберите COM-порт. Проверки запустятся автоматически; кнопка «Проверить» повторит цикл.</p><details><summary>Справка</summary><p>Программа 0.2.2 совместима с HEX 0.2.1: если он уже установлен, достаточно обновить EXE. Полный HEX записывает загрузчик с 0x08000000 и приложение с 0x08020000; последние сектора параметров не включены. Используйте только файл своей ревизии.</p><p>LED мигает, пока прошивка работает. В приложении остаются только автоматические проверки: IMU, барометры, SD-карта, Flash, USB и регистр OSD. SD-тест создаёт, проверяет и удаляет отдельный временный файл, сохраняя существующие файлы.</p><p>При кратком обрыве приложение ожидает ту же USB-плату и учитывает смену номера COM. Журнал сеанса сохраняется. Если подключение не возвращается, переподключите USB.</p><p>Если COM-порта нет: проверьте кабель с передачей данных, снимите BOOT0 после записи, перезапустите плату. Если доступен только DFU, повторите запись полного HEX своей платы. Не меняйте защиту MCU и option bytes без необходимости.</p><p>Зелёный статус относится к перечисленным автоматическим проверкам. Электрические выходы и видеотракт этим циклом не проверяются. На графиках показаны физические единицы и последние 10, 30 или 60 секунд; пауза останавливает просмотр, запись продолжается.</p><p><a href="./#hardware-reference">Выводы, RCIN, серво и DShot</a> · <a href="diagnostics/MyboxDiag-0.2.2-sources.zip" download>Исходники и полная инструкция</a></p></details></main></body></html>'
 (site/'diagnostics.html').write_text(page,encoding='utf-8')
 with zipfile.ZipFile(dest/'MyboxDiag-0.2.2-sources.zip','w',zipfile.ZIP_DEFLATED) as z:
  for folder in ['firmware','pc','profiles','config','tools','tests','docs','hardware']:
   for p in (KIT/folder).rglob('*'):
    if p.is_file() and not any(part in ('__pycache__','.venv') for part in p.parts) and p.suffix not in ('.pyc',):z.write(p,p.relative_to(KIT))
  for f in (KIT/'site-source').rglob('*'):
   rel=f.relative_to(KIT/'site-source')
   if f.is_file() and 'diagnostics' not in rel.parts and f.name!='firmware-index.json' and f.suffix in ('.html','.css','.js','.json','.png'):z.write(f,f.relative_to(KIT))
  for name in ['README.ru.md','LICENSE']:z.write(KIT/name,name)
  for f in (KIT/'examples/demo-report').glob('*'):
   if f.is_file():z.write(f,f.relative_to(KIT))
  for name in ['demo-window.png','demo-imu-chart.png','demo-baro-chart.png','test-results.txt','site-baseline-tests.txt']:
   z.write(KIT/'examples'/name,'examples/'+name)
 print('Packaged 3 full HEX, 1 standalone EXE and sources')
if __name__=='__main__':main()
