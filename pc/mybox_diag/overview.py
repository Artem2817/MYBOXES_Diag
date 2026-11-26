"""Plain module health summaries; incomplete evidence never becomes a green pass."""
MODULES=[('imu','IMU','Движение и положение'),('baro','Барометры','Давление и высота'),('sd','SD-карта','Чтение и запись'),('flash','Flash','Внутренняя память'),('usb','USB','Связь с компьютером'),('osd','OSD','Микросхема видеовыхода')]
COLORS={'neutral':'#8d96aa','good':'#65e6a7','attention':'#ffd166','bad':'#ff727e'}

def module_for(key):
    for prefix,module in [('imu','imu'),('baro','baro'),('adc','power'),('sd','sd'),('flash','flash'),('usb','usb'),('osd','osd'),('pwm','outputs')]:
        if key.startswith(prefix):return module
    return 'signals' if key.startswith(('led','safety','buzzer','heater')) else 'ports'

def test_label(key):
    if key=='sd.read':return 'Наличие и объём карты'
    if key=='sd.write':return 'Запись и чтение файла'
    device,_,method=key.partition('.')
    labels={'id':'Обнаружение','stream':'Поток измерений','rest':'Покой','motion':'Повороты','selftest':'Самотест','compare':'Сравнение IMU','register':'Регистры','video':'Изображение','read':'Чтение','write':'Запись','voltage':'Напряжение','current':'Ток','pressure':'Давление','rssi':'RSSI','link':'Обмен с ПК','loopback':'Перемычка TX–RX','frames':'Приём сигнала','external':'Внешнее устройство','visual':'Светодиод','button':'Кнопка','led':'Светодиод Safety','audio':'Звук','scope':'Сигнал на выходе'}
    name=labels.get(method,method)
    if device.startswith('imu') and device[3:].isdigit():return f'IMU {int(device[3:])+1} · {name}'
    if device.startswith('baro') and device[4:].isdigit():return f'Барометр {int(device[4:])+1} · {name}'
    if device.startswith(('uart','can','pwm')) or device in ('sd','flash','rcin','i2c','mag'):return f'{device.upper()} · {name}'
    if device=='heater':return 'Нагреватель'
    return name

def module_health(tests,results,connected,complete,fresh=None):
    applicable=[key for key,value in tests.items() if value.get('applicable',True)]
    passed=sum(results.get(key,{}).get('state')=='passed' for key in applicable)
    count=f'{passed} / {len(applicable)} проверок' if applicable else 'Ожидание проверки'
    if not connected:return 'neutral','Нет связи',count
    if any(results.get(key,{}).get('state')=='failed' for key in applicable):return 'bad','Ошибка',count
    if fresh is False:return 'attention','Нет свежих данных',count
    if any(results.get(key,{}).get('state')=='running' for key in applicable):return 'attention','Проверяем…',count
    if not complete:return 'neutral','Получаем данные…',count
    if not applicable:return 'neutral','Не используется','В этой ревизии'
    if passed==len(applicable):return 'good','В норме',count
    if any(results.get(key,{}).get('state') in ('warning','needs_action') for key in applicable):return 'attention','Есть замечания',count
    return 'neutral','Ожидание теста',count
