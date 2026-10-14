"""A wrapping native layout for compact controls and active filter chips."""
from PySide6.QtCore import QRect,QSize,Qt
from PySide6.QtWidgets import QLayout

class FlowLayout(QLayout):
    def __init__(self,parent=None,spacing=6):
        super().__init__(parent);self.items=[];self.setContentsMargins(0,0,0,0);self.setSpacing(spacing)
    def addItem(self,item):self.items.append(item)
    def count(self):return len(self.items)
    def itemAt(self,index):return self.items[index] if 0<=index<len(self.items) else None
    def takeAt(self,index):return self.items.pop(index) if 0<=index<len(self.items) else None
    def expandingDirections(self):return Qt.Orientation(0)
    def hasHeightForWidth(self):return True
    def heightForWidth(self,width):return self.arrange(QRect(0,0,width,0),True)
    def minimumSize(self):
        size=QSize()
        for item in self.items:
            if not item.isEmpty():size=size.expandedTo(item.minimumSize())
        left,top,right,bottom=self.getContentsMargins()
        return size+QSize(left+right,top+bottom)
    def sizeHint(self):return self.minimumSize()
    def setGeometry(self,rect):super().setGeometry(rect);self.arrange(rect,False)
    def arrange(self,rect,test):
        left,top,right,bottom=self.getContentsMargins()
        original=rect
        rect=rect.adjusted(left,top,-right,-bottom)
        x,y,height=rect.x(),rect.y(),0
        for item in self.items:
            if item.isEmpty():continue
            size=item.sizeHint()
            if x>rect.x() and x+size.width()>rect.right()+1:
                x=rect.x();y+=height+self.spacing();height=0
            if not test:item.setGeometry(QRect(x,y,size.width(),size.height()))
            x+=size.width()+self.spacing();height=max(height,size.height())
        return y+height-original.y()+bottom
