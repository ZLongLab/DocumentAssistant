import math
from PySide6.QtCore import QRectF

def crop_selection(image,rect,logical_size):
    rect=QRectF(rect).normalized().intersected(QRectF(0,0,logical_size.width(),logical_size.height()))
    if rect.width()<2 or rect.height()<2 or image.isNull():raise ValueError('请框选至少 2 × 2 的区域')
    sx,sy=image.width()/logical_size.width(),image.height()/logical_size.height()
    left,top=max(0,math.floor(rect.left()*sx)),max(0,math.floor(rect.top()*sy))
    right,bottom=min(image.width(),math.ceil(rect.right()*sx)),min(image.height(),math.ceil(rect.bottom()*sy))
    cropped=image.copy(left,top,right-left,bottom-top);cropped.setDevicePixelRatio(1);return cropped
