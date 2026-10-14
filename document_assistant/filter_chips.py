from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget,QPushButton
from .ui_flow import FlowLayout

class FilterChips(QWidget):
    def __init__(self,window):
        super().__init__();self.window=window;self.flow=FlowLayout(self,6);self.pending=False
        self.fields=[('分类',window.search_category),('搜索范围',window.search_scope),
            ('课程',window.filter_combos['course']),('项目',window.filter_combos['project']),('标签',window.filter_combos['tag']),
            ('正文',window.quality_filter),('阅读',window.reading_filter),('排序',window.search_sort)]
        for _,combo in self.fields:combo.currentTextChanged.connect(self.schedule)
        self.rebuild()
    def schedule(self,*_):
        if self.pending:return
        self.pending=True;QTimer.singleShot(0,self.rebuild)
    def rebuild(self):
        self.pending=False
        while self.flow.count():
            item=self.flow.takeAt(0);item.widget().hide();item.widget().deleteLater()
        for title,combo in self.fields:
            value=combo.currentText()
            if value==combo.itemText(0):continue
            button=QPushButton(title+'：'+(value[:18]+'…' if len(value)>18 else value)+'  ×')
            button.setObjectName('filterChip');button.setToolTip('移除 '+title+'：'+value)
            button.clicked.connect(lambda checked=False,c=combo:self.clear(c));self.flow.addWidget(button)
        self.setVisible(self.flow.count()>0);self.flow.invalidate();self.updateGeometry()
    def clear(self,combo):
        combo.setCurrentIndex(0)
        if combo.isEditable():combo.setEditText(combo.itemText(0))

