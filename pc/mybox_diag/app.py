from __future__ import annotations
import argparse,collections,json,math,re,shutil,sys,time
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt,QTimer,QPointF
from PySide6.QtGui import QColor,QFont,QPainter,QPen,QPolygonF
from PySide6.QtWidgets import QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QPushButton,QLabel,QComboBox,QCheckBox,QTabWidget,QTreeWidget,QTreeWidgetItem,QSplitter,QTextEdit,QFileDialog,QMessageBox,QSpinBox,QGroupBox,QFrame,QScrollArea,QDialog,QToolButton,QMenu,QStackedWidget
import pyqtgraph as pg
from serial.tools import list_ports
from .transport import Connection
from .ports import capture_port,find_port,is_slcan
from .overview import MODULES,module_for,module_health,COLORS,test_label
from .widgets import ModuleCard,ModuleDetails
from .automatic import CATALOG,AutoRunner
from .charts import ChartsDialog,chart_values
from . import __version__
from .session import Session,STATES
from .orientation import Orientation,rotation,euler
from .instructions import CODES

class BoardView(QWidget):
    def __init__(self):
        super().__init__();self.setMinimumSize(400,280);self.q=np.array([1.,0,0,0]);self.text='Ожидание IMU'
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.fillRect(self.rect(),QColor('#111622'))
        p.setPen(QPen(QColor(69,224,255,12),1))
        for x in range(0,self.width(),32):p.drawLine(x,0,x,self.height())
        for y in range(0,self.height(),32):p.drawLine(0,y,self.width(),y)
        scale=min(self.width()/3.6,self.height()/3.0)
        # Fixed camera looks down on a spatial board; attitude comes from IMU quaternion.
        camera=np.array([[.75,-.66,0],[.33,.38,-.86],[.57,.65,.51]])
        r=camera@rotation(self.q)
        def project(v):
            x,y,z=r@np.array(v);perspective=4/(4-z);return QPointF(self.width()/2+x*scale*perspective,self.height()/2-y*scale*perspective)
        corners=[[-1,-.65,0],[1,-.65,0],[1,.65,0],[-1,.65,0]]
        p.setPen(QPen(QColor('#29777a'),1));p.setBrush(QColor('#12383f'));p.drawPolygon(QPolygonF([project([x,y,-.12]) for x,y,z in corners]))
        top=QPolygonF([project(v) for v in corners]);p.setPen(QPen(QColor('#45e0ff'),2));p.setBrush(QColor('#174b4d'));p.drawPolygon(top)
        p.setPen(QPen(QColor('#287275'),1))
        for y in [-.4,-.2,.2,.4]:p.drawLine(project([-.7,y,.02]),project([.65,y,.02]))
        for x in [-.9,.9]:
            for y in [-.4,-.2,0,.2,.4]:
                p.setPen(QPen(QColor('#e5bf73'),3));p.drawLine(project([x-.04,y,.03]),project([x+.04,y,.03]))
        p.setBrush(QColor('#192333'));p.drawPolygon(QPolygonF([project(v) for v in [[-.25,-.25,.02],[.25,-.25,.02],[.25,.25,.02],[-.25,.25,.02]]]))
        for x in [-.82,.82]:
            for y in [-.48,.48]:p.setBrush(QColor('#c4cbd1'));p.drawEllipse(project([x,y,.02]),5,5)
        p.setPen(QPen(QColor('#fff'),3));p.drawLine(project([.35,0,.03]),project([.9,0,.03]));p.drawLine(project([.9,0,.03]),project([.7,.12,.03]));p.drawLine(project([.9,0,.03]),project([.7,-.12,.03]))
        for v,color,text in [([1.4,0,0],'#ff746b','X · ВПЕРЁД'),([0,1.15,0],'#67ef97','Y'),([0,0,.9],'#72adff','Z')]:
            p.setPen(QPen(QColor(color),2));p.drawLine(project([0,0,0]),project(v));p.drawText(project(v)+QPointF(4,0),text)
        p.end()

class Window(QMainWindow):
    def __init__(self,args):
        super().__init__();self.args=args;self.setWindowTitle(f'MYBOX · диагностика {__version__}');self.resize(1320,860);self.setMinimumSize(1040,680)
        self.worker=None;self._workers=[];self.closing=False;self.session=None;self.items={};self.telemetry_items={};self.samples={};self.receipts=collections.defaultdict(lambda:collections.deque(maxlen=200));self.plot_data=collections.defaultdict(lambda:collections.deque(maxlen=12000));self.orientations=collections.defaultdict(Orientation);self._latest_seq={};self.connected=False;self.auto_retry=False;self.last_port=None
        self.port_identity=None
        self.output=Path(args.output).resolve();self.output.mkdir(parents=True,exist_ok=True)
        self._build_ui();self.runner=AutoRunner(self.command,self.auto_failed);self.awaiting_initial=False;self.refresh_ports();self.timer=QTimer(self);self.timer.timeout.connect(self.refresh_view);self.timer.start(50)
        if args.demo or args.smoke_demo:QTimer.singleShot(100,self.connect_demo)
        if args.smoke_demo:
            QTimer.singleShot(3500,self.smoke_finish)
    def _build_ui(self):
        central=QWidget();self.setCentralWidget(central);layout=QVBoxLayout(central);layout.setContentsMargins(26,22,26,18);layout.setSpacing(20)
        bar=QHBoxLayout();brand=QLabel('MYBOX');brand.setObjectName('brand');bar.addWidget(brand)
        label=QLabel('ДИАГНОСТИКА');label.setObjectName('eyebrow');bar.addWidget(label);bar.addStretch()
        self.ports=QComboBox();self.ports.setEditable(True);self.ports.setMinimumWidth(215);self.ports.setMaximumWidth(300);bar.addWidget(self.ports)
        self.refresh_button=QPushButton('↻');self.refresh_button.setToolTip('Обновить порты');self.refresh_button.setFixedWidth(40);self.refresh_button.clicked.connect(self.refresh_ports);bar.addWidget(self.refresh_button)
        self.connect_button=QPushButton('Подключить');self.connect_button.clicked.connect(self.toggle_connection);bar.addWidget(self.connect_button)
        more=QToolButton();more.setText('•••');more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup);menu=QMenu(more)
        menu.addAction('Показания и график',lambda:self.data_dialog.show());menu.addAction('Журнал связи',lambda:self.log_dialog.show());menu.addAction('Настройки',lambda:self.settings_dialog.show());menu.addSeparator();menu.addAction('Демонстрация',self.connect_demo);more.setMenu(menu);bar.addWidget(more);layout.addLayout(bar)
        split=QSplitter(Qt.Orientation.Horizontal);split.setChildrenCollapsible(False);layout.addWidget(split,1)
        left=QFrame();left.setObjectName('orientationPanel');left.setMinimumWidth(360);ll=QVBoxLayout(left);ll.setContentsMargins(22,22,22,22);ll.setSpacing(12)
        top=QHBoxLayout();label=QLabel('Положение платы');label.setObjectName('sectionTitle');top.addWidget(label);top.addStretch();self.board_name=QLabel('MYBOX');self.board_name.setObjectName('eyebrow');top.addWidget(self.board_name);ll.addLayout(top)
        self.banner=QLabel('Подключите плату по USB');self.banner.setObjectName('muted');self.banner.setWordWrap(True);ll.addWidget(self.banner)
        self.view=BoardView();self.view.setMinimumSize(300,260);ll.addWidget(self.view,1)
        self.angles=QLabel('Крен —    Тангаж —\nКурс — · относительный');self.angles.setObjectName('angles');self.angles.setAlignment(Qt.AlignmentFlag.AlignCenter);ll.addWidget(self.angles)
        self.orientation_status=QLabel('Ожидание измерений');self.orientation_status.setObjectName('muted');self.orientation_status.setWordWrap(True);self.orientation_status.setAlignment(Qt.AlignmentFlag.AlignCenter);ll.addWidget(self.orientation_status)
        orient_controls=QHBoxLayout();self.imu_select=QComboBox();self.imu_select.addItem('IMU 1','imu0');orient_controls.addWidget(self.imu_select);orient_controls.addStretch();b=QPushButton('Установить ноль');b.clicked.connect(self.zero);orient_controls.addWidget(b);ll.addLayout(orient_controls);split.addWidget(left)
        right=QWidget();right.setMinimumWidth(510);rl=QVBoxLayout(right);rl.setContentsMargins(8,0,0,0);rl.setSpacing(14)
        heading=QHBoxLayout();title=QLabel('Оборудование');title.setObjectName('sectionTitle');heading.addWidget(title);heading.addStretch();self.full=QPushButton('Проверить');self.full.setFixedWidth(135);self.full.setObjectName('primary');self.full.setEnabled(False);self.full.clicked.connect(self.run_full);heading.addWidget(self.full)
        self.stop_button=QPushButton('Стоп');self.stop_button.setEnabled(False);self.stop_button.clicked.connect(self.stop_tests);heading.addWidget(self.stop_button);rl.addLayout(heading)
        container=QWidget();grid=QGridLayout(container);grid.setContentsMargins(0,0,0,0);grid.setSpacing(10);self.cards={};self.module_details={}
        for i,(key,title,subtitle) in enumerate(MODULES):
            card=ModuleCard(key,title,subtitle,self.select_module);grid.addWidget(card,i//2,i%2);self.cards[key]=card
        grid.setColumnStretch(0,1);grid.setColumnStretch(1,1);rl.addWidget(container)
        panel=QFrame();panel.setObjectName('detailsPanel');details_layout=QVBoxLayout(panel);details_layout.setContentsMargins(18,16,18,16);details_layout.setSpacing(12)
        self.details_title=QLabel('IMU');self.details_title.setObjectName('cardTitle');details_layout.addWidget(self.details_title)
        self.details_stack=QStackedWidget();self.details_stack.setMinimumHeight(120);details_layout.addWidget(self.details_stack,1)
        for key,title,subtitle in MODULES:
            content=ModuleDetails(key);self.module_details[key]=content
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame);scroll.setWidget(content);self.details_stack.addWidget(scroll)
        rl.addWidget(panel,1);self.select_module('imu')
        footer=QHBoxLayout();self.summary=QLabel('Готово к подключению');self.summary.setObjectName('muted');footer.addWidget(self.summary,1);b=QPushButton('Сохранить отчёт');b.clicked.connect(self.export);footer.addWidget(b);rl.addLayout(footer);split.addWidget(right);split.setSizes([470,770])
        self.log_dialog=QDialog(self);self.log_dialog.setWindowTitle('MYBOX · журнал связи');self.log_dialog.resize(850,500);log_layout=QVBoxLayout(self.log_dialog);self.log=QTextEdit();self.log.setReadOnly(True);self.log.document().setMaximumBlockCount(1500);log_layout.addWidget(self.log)
        self.settings_dialog=QDialog(self);self.settings_dialog.setWindowTitle('Настройки');self.settings_dialog.resize(480,300);settings=QVBoxLayout(self.settings_dialog)
        self.reconnect=QCheckBox('Подключаться снова при обрыве USB');self.reconnect.setChecked(True);settings.addWidget(self.reconnect)
        self.rate=QSpinBox();self.rate.setRange(0,100);self.rate.setValue(20);self.rate.setSuffix(' Гц');settings.addWidget(QLabel('Частота передачи показаний'));settings.addWidget(self.rate);b=QPushButton('Применить частоту');b.clicked.connect(lambda:self.command('stream',rate=self.rate.value()));settings.addWidget(b)
        self.profile=QComboBox();self.profile.addItems(['MyboxH743_mini','MyboxH743_mini_v2','MyboxH743_mini_v2_vib']);self.profile.setCurrentIndex(2);settings.addWidget(QLabel('Профиль для демонстрации'));settings.addWidget(self.profile)
        self.board_info=QLabel('Плата не подключена');self.board_info.setWordWrap(True);self.board_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);settings.addWidget(self.board_info)
        self.data_dialog=ChartsDialog(self.plot_data,self);self.sensor_tree=self.data_dialog.sensor_tree;self.raw=self.data_dialog.raw;self.link_stats=self.data_dialog.link_stats
        self.setStyleSheet("""
            QWidget{font-family:'Segoe UI',Arial;font-size:13px;color:#f4f7fb;background:#080b12;}
            QFrame#orientationPanel,QFrame#moduleCard,QFrame#detailsPanel{background:#111622;border:1px solid #262c39;border-radius:18px;}
            QFrame#orientationPanel QLabel,QFrame#moduleCard QLabel,QFrame#moduleCard QWidget,QFrame#detailsPanel QWidget{background:transparent;}
            QLabel#brand{font-size:25px;font-weight:800;letter-spacing:2px;}
            QLabel#eyebrow{color:#45e0ff;font-size:10px;font-weight:700;letter-spacing:2px;}
            QLabel#sectionTitle{font-size:20px;font-weight:600;}
            QLabel#muted{color:#8d96aa;font-size:11px;}
            QLabel#angles{font-size:17px;line-height:2;color:#f4f7fb;}
            QLabel#cardTitle{font-size:17px;font-weight:600;}
            QLabel#cardState{font-size:12px;}
            QLabel#liveData{font-size:12px;color:#45e0ff;}
            QPushButton,QToolButton{border:1px solid #303747;border-radius:11px;padding:10px 14px;background:#111622;}
            QPushButton:hover,QToolButton:hover{border-color:#45e0ff;background:#15232f;}
            QPushButton:disabled{color:#606a7c;border-color:#222936;background:#0d121d;}
            QPushButton#primary{background:#45e0ff;color:#001018;border-color:#45e0ff;font-weight:600;}
            QPushButton#primary:hover{background:#80eaff;}
            QPushButton#primary:disabled{background:#17343e;color:#69818c;border-color:#17343e;}
            QPushButton#cardHeader{background:transparent;border:0;padding:0;text-align:left;}
            QFrame#testRow{background:#0d121e;border:1px solid #272f3d;border-radius:8px;}
            QFrame#moduleCard[selected="true"]{border-color:#45e0ff;background:#10202b;}
            QComboBox,QSpinBox{background:#111622;border:1px solid #303747;border-radius:10px;padding:9px;}
            QComboBox QAbstractItemView,QMenu{background:#111622;border:1px solid #303747;padding:6px;selection-background-color:#183443;}
            QMenu::item{padding:9px 16px;} QMenu::item:selected{background:#183443;}
            QTreeWidget,QTextEdit{background:#0d121e;border:1px solid #272f3d;border-radius:8px;padding:7px;selection-background-color:#1b4050;}
            QHeaderView::section{background:#111622;padding:7px;border:0;color:#8d96aa;}
            QSplitter::handle{background:#080b12;width:12px;}
            QScrollBar:vertical{background:transparent;width:7px;margin:0;} QScrollBar::handle:vertical{background:#303747;border-radius:3px;min-height:28px;} QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}
            QStatusBar{color:#8d96aa;font-size:11px;}
        """)
    def toggle_connection(self):
        if self.auto_retry or (self.worker and self.worker.isRunning()):self.disconnect()
        else:self.connect_port()
    def select_module(self,key):
        for name,card in self.cards.items():card.set_selected(name==key)
        index=next(i for i,value in enumerate(MODULES) if value[0]==key)
        self.details_title.setText(MODULES[index][1]);self.details_stack.setCurrentIndex(index)
    def selected_port(self):
        index=self.ports.currentIndex();text=self.ports.currentText().strip()
        return self.ports.itemData(index) if index>=0 and text==self.ports.itemText(index) else text
    def refresh_ports(self):
        previous=self.selected_port();self.ports.clear()
        ports=sorted((p for p in list_ports.comports() if not is_slcan(p)),key=lambda p:(not (p.vid in (0x0483,0x1209) or 'mybox' in (p.description or '').lower()),p.device))
        for p in ports:self.ports.addItem(f'{p.device} · {p.description}',p.device)
        for i in range(self.ports.count()):
            if self.ports.itemData(i)==previous:self.ports.setCurrentIndex(i);break
    def _new_session(self,demo):
        if self.session:self.session.close()
        self.session=Session(demo);self.session.start_recording(self.output);self.items.clear();self.samples.clear();self.sensor_tree.clear();self.telemetry_items.clear();self.plot_data.clear();self.data_dialog.reset();self.receipts.clear();self.orientations.clear();self._latest_seq.clear()
        self.runner.cancel()
        for card in self.cards.values():card.clear()
        for detail in self.module_details.values():detail.clear()
    def _connect(self,port=None,demo=False,retry=False):
        if self.closing:return
        if self.worker and self.worker.isRunning():self.disconnect();QTimer.singleShot(200,lambda:self._connect(port,demo));return
        if not retry:
            self._new_session(demo)
            self.port_identity=capture_port(port,list_ports.comports()) if not demo else None
        else:
            self.session.catalog_complete=False;self.session.catalog_seen.clear();self.session.tests.clear();self.session.results.clear();self.items.clear()
            self.runner.cancel()
            for card in self.cards.values():card.clear()
            for detail in self.module_details.values():detail.clear()
        self.auto_retry=not demo;self.last_port=port;self.connected=False
        self.awaiting_initial=True
        w=Connection(port=port,demo=demo,profile=self.profile.currentText(),rate=self.rate.value());self.worker=w;self._workers.append(w)
        w.frames.connect(lambda f:self.on_frames(f) if self.worker is w else None);w.status.connect(lambda t:self.on_status(t) if self.worker is w else None);w.fault.connect(lambda t:self.on_fault(t) if self.worker is w else None);w.stats.connect(lambda t:self.on_stats(t) if self.worker is w else None);w.finished.connect(lambda:self._finished(w));w.start()
    def connect_port(self):
        port=self.selected_port()
        if not port:self.on_fault('Выберите или введите COM-порт');return
        self._connect(port)
    def connect_demo(self):self._connect(demo=True)
    def disconnect(self):
        self.auto_retry=False;self.awaiting_initial=False;self.runner.cancel()
        self.connect_button.setText('Подключить');self.banner.setText('Отключено')
        if self.worker:self.worker.stop()
        if self.session and (not self.worker or not self.worker.isRunning()):self.session.close()
    def _finished(self,w):
        if w in self._workers:self._workers.remove(w)
        if self.worker is w:
            self.connected=False
            self.runner.cancel()
            if self.auto_retry and self.reconnect.isChecked():QTimer.singleShot(2000,self._retry)
            elif self.session:self.session.close()
    def _retry(self):
        if self.closing or not self.auto_retry or not self.reconnect.isChecked() or (self.worker and self.worker.isRunning()):return
        port=find_port(self.port_identity,list_ports.comports())
        if port:self._connect(port,retry=True)
        else:
            self.banner.setText('Ожидание платы USB…');self.connect_button.setText('Отменить')
            QTimer.singleShot(2000,self._retry)
    def on_status(self,text):
        if self.session:self.session.note('connection',state=text)
        self.connected=text in ('Подключено','ДЕМОНСТРАЦИЯ');self.banner.setText('Демонстрация · данные смоделированы' if text=='ДЕМОНСТРАЦИЯ' else text)
        self.connect_button.setText('Отключить' if self.connected else 'Подключить');self.full.setEnabled(self.connected);self.stop_button.setEnabled(self.connected)
        self.banner.setStyleSheet('color:#ffd166' if text=='ДЕМОНСТРАЦИЯ' else 'color:#8d96aa')
    def on_fault(self,text):
        self.log.append('Ошибка / событие: '+text)
        if not self.connected:self.banner.setText('Нет связи · ожидание платы' if self.auto_retry else 'Не удалось подключиться')
        else:self.statusBar().showMessage('Проверка не завершена. Подробности в меню «•••» → «Журнал связи».',5000)
        if self.session:self.session.note('transport_error',detail=text)
    def on_stats(self,stats):
        if self.session:self.session.transport=stats
        self.link_stats.setText(f"USB · получено кадров: {stats['received_frames']} · пропуски: {stats['missing_frames']} · повреждения: {stats['parser_errors']} · ожидают ответа: {stats['pending']}")
    def command(self,op,**kw):
        if self.worker and self.worker.isRunning():return self.worker.request(op,**kw)
        self.on_fault('Устройство не подключено')
    def on_frames(self,frames):
        if not self.session or self.closing:return
        now=time.monotonic()
        for f in frames:
            b=f.body
            if f.kind==2 and b.get('op')=='info':
                if self.session.board and self.session.board.get('uid')!=b.get('uid'):self._new_session(bool(b.get('demo')))
                self.board_info.setText(f"{b['profile']} · {b['mcu']} · UID {b['uid']} · {b['firmware']} · сборка {b['build_id']} · протокол {b['protocol']}\nРевизия из сборки; аппаратное определение ревизии отсутствует. Запись сеанса включена.")
                self.data_dialog.set_board(b)
                self.imu_select.clear()
                for i in range(b.get('imu_count',1)):self.imu_select.addItem(f'IMU {i+1}',f'imu{i}')
                self.board_name.setText({'MyboxH743_mini':'MINI','MyboxH743_mini_v2':'MINI V2','MyboxH743_mini_v2_vib':'MINI V2 VIB'}.get(b.get('profile'),'MYBOX'))
            self.session.ingest(f);self.runner.handle(f)
            if f.kind==3:
                event=b.get('event')
                if event in ('test','result'):
                    key=b['test']
                    if key in CATALOG and self.session.tests.get(key,{}).get('applicable',True):self.module_details[module_for(key)].update_test(key,self.session.results.get(key,{}))
                elif event=='results_complete' and self.awaiting_initial and self.session.catalog_valid and self.connected:
                    self.awaiting_initial=False;self.run_full()
                elif event=='error':self.log.append(json.dumps(b,ensure_ascii=False))
            if f.kind==4:
                sensor=b['sensor'];self.samples[sensor]=(b,now,f.time_ms);self.receipts[sensor].append(now)
                if sensor.startswith('imu'):self.orientations[sensor].update(b)
                for key,value in chart_values(b).items():self.plot_data[key].append((now,value))
    def refresh_view(self):
        if not self.session:return
        self.runner.tick();self.refresh_modules()
        self.full.setEnabled(self.connected and self.session.catalog_valid and not self.runner.busy);self.full.setText('Проверяем…' if self.runner.busy else 'Проверить')
        sensor=(self.imu_select.currentData() or 'imu0');o=self.orientations[sensor];
        if sensor in self.samples and time.monotonic()-self.samples[sensor][1]>max(.5,2/max(self.rate.value(),1)):o.state='Нет свежих данных на ПК; ориентация не обновляется'
        q=o.display_q;self.view.q=q;self.view.text='';self.view.update();r,p,y=euler(q)
        self.angles.setText(f'Крен {r:.1f}°    Тангаж {p:.1f}°\nКурс {y:.1f}° · относительный')
        self.orientation_status.setToolTip(o.state)
        fresh=sensor in self.samples and time.monotonic()-self.samples[sensor][1]<max(.5,2/max(self.rate.value(),1)) and self.samples[sensor][0].get('fresh',False)
        self.orientation_status.setText('Ориентация обновляется' if self.connected and fresh else 'Нет свежих показаний IMU' if self.connected else 'Плата отключена')
        if sensor in self.samples:
            b,stamp,frame_ms=self.samples[sensor];self.raw.setText(f"АЦП IMU: {b.get('raw')}\nУскорение, м/с²: {[round(v,4) for v in b.get('accel_m_s2',[])]} · Гироскоп, °/с: {[round(v,4) for v in b.get('gyro_deg_s',[])]}\nТемпература: {b.get('temperature_c')} °C · поправка нуля гироскопа, °/с: {o.bias.round(4).tolist()}")
        now=time.monotonic()
        for sensor,(b,received,frame_ms) in self.samples.items():
            receipt=self.receipts[sensor];hz=(len(receipt)-1)/(receipt[-1]-receipt[0]) if len(receipt)>1 and receipt[-1]>receipt[0] else 0
            age=max(0,(now-received)*1000)+max(0,((frame_ms-b.get('sample_ms',frame_ms))&0xffffffff))
            units={'temperature_c':'°C','pressure_pa':'Па','relative_altitude_m':'м','accel_m_s2':'м/с²','gyro_deg_s':'°/с','raw':'отсчёты','value':b.get('units',''),'adc_voltage_v':'В','scale':'коэффициент'}
            for key,unit in units.items():
                if key not in b:continue
                values=b[key] if isinstance(b[key],list) else [b[key]]
                for i,value in enumerate(values):
                    name=f'{sensor}.{key}'+(f'.{i}' if len(values)>1 else '')
                    item=self.telemetry_items.get(name)
                    if item is None:item=QTreeWidgetItem();self.sensor_tree.addTopLevelItem(item);self.telemetry_items[name]=item
                    cols=[name,f'{value:.5g}' if isinstance(value,(float,int)) else str(value),unit,f'{age:.0f}'+(' · нет свежих' if not b.get('fresh') or now-received>max(.5,2/max(self.rate.value(),1)) else ''),str(b.get('measurement_hz','—')),f'{hz:.1f}' if now-received<2 else '0',str(b.get('errors','—'))]
                    for k,text in enumerate(cols):item.setText(k,text)
        if self.data_dialog.isVisible():self.data_dialog.stale_after=max(.6,2/max(self.rate.value(),1));self.data_dialog.refresh()
    def refresh_modules(self):
        now=time.monotonic();levels=[]
        for module,title,subtitle in MODULES:
            tests={key:value for key,value in self.session.tests.items() if module_for(key)==module}
            fresh=None;live=[]
            if module in ('imu','baro'):
                count=self.session.board.get('imu_count' if module=='imu' else 'barometer_count',0)
                readings=[self.samples.get(f'{module}{i}') for i in range(count)]
                if count:
                    fresh=all(value and now-value[1]<max(.5,2/max(self.rate.value(),1)) and value[0].get('fresh',False) for value in readings)
                for i,value in enumerate(readings):
                    if value:
                        body=value[0];temperature=body.get('temperature_c');pressure=body.get('pressure_pa')
                        parts=[f'{temperature:.1f} °C'] if isinstance(temperature,(float,int)) else []
                        if isinstance(pressure,(float,int)):parts.append(f'{pressure/100:.1f} гПа')
                        live.append(f'{"IMU" if module=="imu" else "Барометр"} {i+1} · '+ ' · '.join(parts))
            if module=='sd':
                for key in ('sd.read','sd.write'):
                    result=self.session.results.get(key,{})
                    values=dict(re.findall(r'(\w+)\s+(-?\d+)',result.get('actual','')))
                    if key=='sd.read' and int(values.get('capacity_bytes',0))>0:
                        live.append(f"Объём: {int(values['capacity_bytes'])/1024**3:.1f} ГБ · свободно: {int(values.get('free_bytes',0))/1024**3:.1f} ГБ")
                    if key=='sd.write' and result.get('state')=='passed':live.append('Запись и чтение совпали · тестовый файл удалён')
            complete=self.session.catalog_valid
            card=self.cards[module];level,state,count=module_health(tests,self.session.results,self.connected,complete,fresh)
            card.set_health(level,state,count);detail=self.module_details[module];detail.live.setText('\n'.join(live));detail.live.setVisible(bool(live));levels.append(level)
        good=levels.count('good');bad=levels.count('bad')
        self.summary.setText(('Демо · ' if self.session.demo else '')+(f'Ошибки: {bad} · проверено блоков: {good}/{len(MODULES)}' if bad else f'Проверено блоков: {good}/{len(MODULES)}'))
        self.summary.setToolTip(self.session.conclusion()+' · запись отчёта выполняется автоматически')
    def zero(self):self.orientations[(self.imu_select.currentData() or 'imu0')].reset_zero()
    def run_full(self):
        if not self.connected or not self.session or not self.session.catalog_valid or self.runner.busy:return
        self.session.results.clear()
        for key,test in self.session.tests.items():
            if test.get('applicable',True):self.module_details[module_for(key)].update_test(key,{})
        self.runner.start([key for key,test in self.session.tests.items() if test.get('applicable',True)])
    def stop_tests(self):
        self.awaiting_initial=False;self.runner.stop()
    def auto_failed(self,key,code):
        if key and self.session:
            result=dict(test=key,state='warning',code=code,detail='Автоматическую проверку не удалось завершить.')
            self.session.results[key]=result;self.module_details[module_for(key)].update_test(key,result)
        self.on_fault(code)
    def export(self):
        if not self.session:return
        directory=QFileDialog.getExistingDirectory(self,'Папка для отчёта',str(self.output))
        if directory:
            report=self.session.export(directory)
            if self.session._csv:self.session._csv.flush()
            source=self.session.directory/'telemetry.csv'
            if source.resolve()!= (Path(directory)/'telemetry.csv').resolve():shutil.copy2(source,Path(directory)/'telemetry.csv')
            self.statusBar().showMessage('Сохранено: '+str(report),10000)
    def smoke_finish(self):
        if not self.session or not self.session.board or not self.session.latest:
            print('DEMO_SMOKE_FAILED',flush=True);QApplication.instance().exit(2);return
        self.refresh_view();self.grab().save(str(self.output/'demo-window.png'))
        self.data_dialog.show();QApplication.processEvents()
        for group in ('imu','baro'):
            self.data_dialog.select_group(group);self.data_dialog.refresh();QApplication.processEvents();self.data_dialog.grab().save(str(self.output/f'demo-{group}-chart.png'))
        self.data_dialog.close();self.session.export(self.output/'demo-report');self.session._csv.flush();shutil.copy2(self.session.directory/'telemetry.csv',self.output/'demo-report/telemetry.csv');print('DEMO_SMOKE_OK',flush=True);self.close()
    def closeEvent(self,event):
        self.closing=True
        self.runner.cancel();self.auto_retry=False
        for w in self._workers:w.stop()
        for w in list(self._workers):
            if not w.wait(1500):event.ignore();QTimer.singleShot(1000,self.close);return
        if self.session:self.session.close()
        event.accept()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--demo',action='store_true');parser.add_argument('--smoke-demo',action='store_true');parser.add_argument('--output',default='MyboxReports');args=parser.parse_args()
    app=QApplication(sys.argv[:1]);pg.setConfigOptions(antialias=False);window=Window(args);window.show();return app.exec()
if __name__=='__main__':raise SystemExit(main())
