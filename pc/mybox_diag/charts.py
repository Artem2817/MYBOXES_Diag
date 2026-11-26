"""Bench plots: named measurements, physical units, and a rolling seconds axis."""
import math,time
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,QComboBox,QCheckBox,QStackedWidget,QTreeWidget

AXES=['#ff727e','#65e6a7','#45e0ff']

def chart_values(body):
    sensor=body.get('sensor','');fields=('accel_m_s2','gyro_deg_s','temperature_c') if sensor.startswith('imu') else ('pressure_pa','relative_altitude_m','temperature_c') if sensor.startswith('baro') else ('value',)
    values={}
    for field in fields:
        if field not in body:continue
        source=body[field];components=source if isinstance(source,list) else [source]
        for i,value in enumerate(components):
            key=f'{sensor}.{field}'+(f'.{i}' if isinstance(source,list) else '')
            values[key]=float(value) if body.get('fresh',False) and isinstance(value,(int,float)) and math.isfinite(value) else float('nan')
    return values

class MeasurementPlot(QWidget):
    def __init__(self,title,unit,suffixes,labels,min_span,scale=1,decimals=2):
        super().__init__();self.unit=unit;self.suffixes=suffixes;self.labels=labels;self.min_span=min_span;self.scale=scale;self.decimals=decimals
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(4)
        self.heading=QLabel(title);self.heading.setObjectName('cardTitle');layout.addWidget(self.heading)
        self.values=QLabel('—');self.values.setTextFormat(Qt.TextFormat.RichText);self.values.setStyleSheet('font-size:17px;');layout.addWidget(self.values)
        self.plot=pg.PlotWidget(background='#0d121e');self.plot.setMinimumHeight(130);self.plot.showGrid(x=True,y=True,alpha=.13);self.plot.setLabel('left',unit);self.plot.setLabel('bottom','Время, с');self.plot.setMouseEnabled(x=False,y=False);self.plot.hideButtons()
        self.plot.getAxis('left').enableAutoSIPrefix(False);self.plot.getAxis('bottom').enableAutoSIPrefix(False)
        self.colors=AXES if len(suffixes)>1 else ['#45e0ff']
        self.curves=[self.plot.plot(pen=pg.mkPen(self.colors[i],width=2),connect='finite') for i in range(len(suffixes))];layout.addWidget(self.plot,1)
    def update_data(self,data,prefix,origin,now,span,stale_after=.6):
        elapsed=now-origin;right=max(span,elapsed);left=max(0,right-span);self.plot.setXRange(left,right,padding=0)
        all_values=[];readouts=[]
        for i,suffix in enumerate(self.suffixes):
            points=data.get(prefix+suffix,());points=[(t-origin,v*self.scale) for t,v in points if now-span<=t<=now]
            array=np.asarray(points,dtype=float)
            self.curves[i].setData(array[:,0],array[:,1]) if len(array) else self.curves[i].setData([],[])
            finite=array[:,1][np.isfinite(array[:,1])] if len(array) else np.array([])
            all_values.extend(finite)
            # A frozen plot keeps its last value; a live stale channel shows a dash.
            value=points[-1][1] if points and now-(points[-1][0]+origin)<stale_after else float('nan')
            text=f'{value:.{self.decimals}f}' if math.isfinite(value) else '—'
            label=(self.labels[i]+' ') if self.labels[i] else ''
            readouts.append(f'<span style="color:{self.colors[i]}">{label}<b>{text}</b> {self.unit}</span>')
        self.values.setText(' &nbsp; &nbsp; '.join(readouts))
        if all_values:
            low,high=min(all_values),max(all_values);width=max(high-low,self.min_span)*1.2;step=self.min_span/10;center=round((low+high)/2/step)*step
            self.plot.setYRange(center-width/2,center+width/2,padding=0)

class ChartsDialog(QDialog):
    def __init__(self,data,parent=None,clock=time.monotonic):
        super().__init__(parent);self.data=data;self.clock=clock;self.origin=clock();self.frozen=None;self.board={};self.pages={};self.group='imu';self.stale_after=.6
        self.setWindowTitle('MYBOX · графики датчиков');self.resize(1120,780);layout=QVBoxLayout(self);layout.setContentsMargins(20,18,20,18);layout.setSpacing(14)
        toolbar=QHBoxLayout();self.group_buttons={}
        for key,title in [('imu','IMU'),('baro','Барометр'),('power','Питание')]:
            button=QPushButton(title);button.setCheckable(True);button.clicked.connect(lambda checked=False,k=key:self.select_group(k));toolbar.addWidget(button);self.group_buttons[key]=button
        toolbar.addStretch();self.sensor=QComboBox();self.sensor.setMinimumWidth(145);toolbar.addWidget(self.sensor);self.span=QComboBox();self.span.setMinimumWidth(125)
        for seconds in (10,30,60):self.span.addItem(f'{seconds} секунд',seconds)
        toolbar.addWidget(self.span);self.pause=QCheckBox('Пауза');self.pause.toggled.connect(self.pause_changed);toolbar.addWidget(self.pause);layout.addLayout(toolbar)
        self.info=QLabel('Ожидание показаний');self.info.setObjectName('muted');layout.addWidget(self.info)
        self.stack=QStackedWidget();layout.addWidget(self.stack,1)
        specs={
            'imu':[
                ('Ускорение','м/с²',[f'.accel_m_s2.{i}' for i in range(3)],['X','Y','Z'],2,1,2),
                ('Угловая скорость','°/с',[f'.gyro_deg_s.{i}' for i in range(3)],['X','Y','Z'],20,1,1)],
            'baro':[
                ('Давление','гПа',['.pressure_pa'],[''],.5,.01,2),
                ('Относительная высота','м',['.relative_altitude_m'],[''],2,1,2)],
            'power':[
                ('Напряжение','В',['adc.voltage.value'],[''],2,1,2),
                ('Ток','А',['adc.current.value'],[''],2,1,2),
                ('Вход давления · напряжение','В',['adc.pressure.value'],[''],.5,1,3),
                ('Вход RSSI','В',['adc.rssi.value'],[''],.5,1,3)]}
        for key in ('imu','baro','power'):
            page=QWidget();grid=QGridLayout(page);grid.setContentsMargins(0,0,0,0);grid.setSpacing(16);plots=[]
            for i,spec in enumerate(specs[key]):
                plot=MeasurementPlot(*spec);grid.addWidget(plot,i//2 if key=='power' else i,i%2 if key=='power' else 0);plots.append(plot)
            self.pages[key]=plots;self.stack.addWidget(page)
        self.table_toggle=QCheckBox('Таблица значений');layout.addWidget(self.table_toggle)
        self.raw_panel=QWidget();raw_layout=QVBoxLayout(self.raw_panel);raw_layout.setContentsMargins(0,0,0,0)
        self.raw=QLabel();self.raw.setWordWrap(True);raw_layout.addWidget(self.raw);self.link_stats=QLabel();raw_layout.addWidget(self.link_stats)
        self.sensor_tree=QTreeWidget();self.sensor_tree.setMaximumHeight(180);self.sensor_tree.setHeaderLabels(['Канал','Значение','Единицы','Возраст, мс','Датчик, Гц','ПК, Гц','Ошибки']);self.sensor_tree.setColumnWidth(0,260);raw_layout.addWidget(self.sensor_tree);layout.addWidget(self.raw_panel);self.raw_panel.hide();self.table_toggle.toggled.connect(self.raw_panel.setVisible)
        self.select_group('imu')
    def reset(self):self.origin=self.clock();self.frozen=None;self.pause.setChecked(False)
    def pause_changed(self,paused):self.frozen=self.clock() if paused else None
    def set_board(self,board):self.board=board;self.select_group(self.group)
    def select_group(self,key):
        previous=self.sensor.currentData();self.group=key;self.stack.setCurrentIndex(('imu','baro','power').index(key));self.sensor.clear()
        count=self.board.get('imu_count' if key=='imu' else 'barometer_count',1) if key!='power' else 0
        for i in range(count):self.sensor.addItem(('IMU ' if key=='imu' else 'Барометр ')+str(i+1),key+str(i))
        index=self.sensor.findData(previous)
        if index>=0:self.sensor.setCurrentIndex(index)
        self.sensor.setVisible(count>1)
        for name,button in self.group_buttons.items():button.setChecked(name==key);button.setObjectName('primary' if name==key else '');button.style().unpolish(button);button.style().polish(button)
        self.refresh()
    def refresh(self):
        now=self.frozen if self.frozen is not None else self.clock();prefix=self.sensor.currentData() or '';span=self.span.currentData()
        for plot in self.pages[self.group]:plot.update_data(self.data,prefix,self.origin,now,span,self.stale_after)
        if self.group=='power':self.info.setText('Напряжение, ток и аналоговые входы');return
        temperatures=self.data.get(prefix+'.temperature_c',());recent=next(((t,v) for t,v in reversed(temperatures) if t<=now),None)
        self.info.setText(f'Температура {recent[1]:.1f} °C' if recent and now-recent[0]<self.stale_after and math.isfinite(recent[1]) else 'Нет свежих показаний')
