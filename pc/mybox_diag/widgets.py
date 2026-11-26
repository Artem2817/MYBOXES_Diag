from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton
from .overview import COLORS,test_label
from .instructions import CODES

class ModuleCard(QFrame):
    """A fixed size selector; opening details never changes the grid geometry."""
    def __init__(self,key,title,subtitle,select,parent=None):
        super().__init__(parent);self.key=key;self.setObjectName('moduleCard');self.setFixedHeight(94)
        layout=QVBoxLayout(self);layout.setContentsMargins(16,12,16,12)
        self.header=QPushButton();self.header.setObjectName('cardHeader');self.header.setMinimumHeight(68);self.header.setAccessibleName(title);self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        line=QHBoxLayout(self.header);line.setContentsMargins(0,0,0,0);line.setSpacing(12)
        self.dot=QLabel('●');self.dot.setFixedWidth(14);line.addWidget(self.dot)
        names=QVBoxLayout();names.setSpacing(3);self.title=QLabel(title);self.title.setObjectName('cardTitle');names.addWidget(self.title)
        self.state=QLabel();self.state.setObjectName('cardState');names.addWidget(self.state)
        self.subtitle=QLabel(subtitle);self.subtitle.setObjectName('muted');names.addWidget(self.subtitle);line.addLayout(names,1)
        self.arrow=QLabel('›');self.arrow.setObjectName('muted');line.addWidget(self.arrow)
        for label in (self.dot,self.title,self.subtitle,self.state,self.arrow):label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.header);self.header.clicked.connect(lambda:select(key));self.set_health('neutral','Ожидание',subtitle)
    def set_selected(self,selected):
        self.setProperty('selected',selected);self.style().unpolish(self);self.style().polish(self);self.update()
    def set_health(self,level,state,subtitle):
        color=COLORS[level];self.dot.setStyleSheet(f'color:{color}');self.state.setStyleSheet(f'color:{color}');self.state.setText(state);self.subtitle.setText(subtitle)
    def clear(self):self.set_health('neutral','Ожидание','Ожидание проверки')

class ModuleDetails(QWidget):
    def __init__(self,key,parent=None):
        super().__init__(parent);self.rows={};layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(8)
        self.live=QLabel();self.live.setObjectName('liveData');self.live.setWordWrap(True);layout.addWidget(self.live)
        self.tests_layout=QVBoxLayout();self.tests_layout.setSpacing(6);layout.addLayout(self.tests_layout)
        scope={'imu':'Связь с датчиком и поступление измерений.','baro':'Связь с датчиком, давление и температура.','sd':'Доступность карты. Запись и чтение временного файла.','flash':'Чтение области с прошивкой.','usb':'Обмен пакетами с компьютером.','osd':'Чтение и проверка регистра OSD.'}
        label=QLabel(scope[key]);label.setObjectName('muted');label.setWordWrap(True);layout.addWidget(label);layout.addStretch()
    def update_test(self,key,result):
        if key not in self.rows:
            row=QFrame();row.setObjectName('testRow');line=QHBoxLayout(row);line.setContentsMargins(10,8,10,8)
            title=QLabel(test_label(key));title.setWordWrap(True);line.addWidget(title,1)
            state=QLabel();line.addWidget(state);row.state_label=state;self.tests_layout.addWidget(row);self.rows[key]=row
        state=result.get('state','not_tested');labels={'passed':'Пройден','failed':'Ошибка','warning':'Замечание','needs_action':'Недоступно','not_tested':'Ожидание','not_applicable':'Не используется','running':'Проверяем…'}
        level='good' if state=='passed' else 'bad' if state=='failed' else 'attention' if state in ('warning','needs_action','running') else 'neutral'
        row=self.rows[key];row.state_label.setText(labels.get(state,state));row.state_label.setStyleSheet(f'color:{COLORS[level]}');row.setToolTip(CODES.get(result.get('code'),result.get('detail','')))
    def clear(self):
        for row in self.rows.values():self.tests_layout.removeWidget(row);row.deleteLater()
        self.rows.clear();self.live.clear()
