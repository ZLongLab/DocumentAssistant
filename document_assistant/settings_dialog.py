import sys
from PySide6.QtCore import QRectF,Qt
from PySide6.QtGui import QColor,QPainter,QPen
from PySide6.QtWidgets import QCheckBox,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QFrame
from .startup_registration import StartupRegistration

class ToggleSwitch(QCheckBox):
    def __init__(self,parent=None):
        super().__init__(parent);self.setFixedSize(44,28);self.setAccessibleName('开机自启动')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    def hitButton(self,pos):return self.rect().contains(pos)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#17604a' if self.isChecked() else '#cad6cf'))
        p.drawRoundedRect(QRectF(1,3,42,22),11,11);p.setBrush(QColor('white'))
        p.drawEllipse(QRectF(24 if self.isChecked() else 4,6,16,16))
        if self.hasFocus():p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor('#448c6e'),1));p.drawRoundedRect(QRectF(0,1,43,26),12,12)
        p.end()

class SettingsDialog(QDialog):
    def __init__(self,window,service=None):
        super().__init__(window);self.window=window;self.service=service or StartupRegistration(window.home)
        self.setWindowTitle('设置 · DocumentAssistant');self.resize(480,300)
        layout=QVBoxLayout(self);layout.setContentsMargins(22,20,22,20);layout.setSpacing(16)
        title=QLabel('启动与快捷操作');title.setStyleSheet('font-size:20px;font-weight:600;color:#173f32');layout.addWidget(title)
        card=QFrame();card.setStyleSheet('QFrame{background:#fffdf9;border:1px solid #e4e3d8;border-radius:12px;} QLabel{border:0;}')
        row=QHBoxLayout(card);row.setContentsMargins(14,14,14,14)
        info=QVBoxLayout();name=QLabel('开机自启动');name.setStyleSheet('font-weight:600;');info.addWidget(name)
        description=QLabel('登录 Windows 后在托盘运行\n无需打开主窗口，即可使用截图快捷键')
        description.setStyleSheet('color:#667068;font-size:12px;');info.addWidget(description);row.addLayout(info,1)
        self.startup_switch=ToggleSwitch();row.addWidget(self.startup_switch)
        layout.addWidget(card);self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        try:self.startup_switch.setChecked(self.service.enabled());self.update_status()
        except OSError as exc:self.status.setText('启动项读取失败：'+str(exc));self.startup_switch.setEnabled(False)
        if sys.platform!='win32':self.startup_switch.setEnabled(False);self.status.setText('开机自启动目前支持 Windows')
        self.startup_switch.toggled.connect(self.toggle_startup)
        actions=QHBoxLayout()
        capture=QPushButton('截图设置');capture.clicked.connect(self.open_capture)
        rules=QPushButton('分类规则');rules.clicked.connect(self.open_rules)
        actions.addWidget(capture);actions.addWidget(rules);actions.addStretch();layout.addLayout(actions)
        close=QPushButton('完成');close.clicked.connect(self.accept);layout.addWidget(close,alignment=Qt.AlignmentFlag.AlignRight)
    def update_status(self):
        self.status.setText('已开启 · 下次登录后自动驻留托盘' if self.startup_switch.isChecked() else '已关闭 · 可随时开启')
        self.status.setStyleSheet('color:#667068;font-size:12px;')
    def toggle_startup(self,enabled):
        try:self.service.set_enabled(enabled)
        except (OSError,ValueError) as exc:
            blocked=self.startup_switch.blockSignals(True)
            try:self.startup_switch.setChecked(self.service.enabled())
            except OSError:self.startup_switch.setChecked(not enabled)
            self.startup_switch.blockSignals(blocked);self.status.setStyleSheet('color:#a54d35;');self.status.setText('设置未成功：'+str(exc));return
        self.update_status()
    def open_capture(self):self.accept();self.window.screenshot_settings()
    def open_rules(self):self.accept();self.window.edit_rules()
