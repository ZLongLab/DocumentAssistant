from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

class LibraryPathLabel(QLabel):
    def __init__(self,text):
        super().__init__();self.full_text='';self.setObjectName('sidebarPath')
        self.setMinimumWidth(0);self.setWordWrap(False);self.setFixedHeight(26);self.setText(text)
    def setText(self,text):self.full_text=str(text);self.refresh()
    def resizeEvent(self,event):super().resizeEvent(event);self.refresh()
    def refresh(self):
        text=self.full_text
        if '\\' in text or '/' in text:
            name=Path(text).name
            QLabel.setText(self,self.fontMetrics().elidedText(name,Qt.TextElideMode.ElideRight,max(1,self.width())))
        else:QLabel.setText(self,text)
        self.setToolTip(text)

