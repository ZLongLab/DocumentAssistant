import math
from PySide6.QtCore import QRect, QRectF


def pixel_scale(image, logical_size):
    """Prefer the screen's native DPR over its rounded logical geometry.

    A 2560px screen at 150% is reported as 1707 logical pixels. Dividing
    2560/1707 squeezes the snapshot and rounds some crop origins one pixel off.
    Synthetic/resized images without matching DPR retain proportional mapping.
    """
    ratio = image.devicePixelRatio()
    tolerance = ratio/2+.01  # rounding the screen geometry to a logical integer
    if (abs(image.width()-logical_size.width()*ratio) <= tolerance and
            abs(image.height()-logical_size.height()*ratio) <= tolerance):
        return ratio,ratio
    return image.width()/max(1,logical_size.width()),image.height()/max(1,logical_size.height())


def selection_pixels(image,rect,logical_size):
    rect=QRectF(rect).normalized().intersected(QRectF(0,0,logical_size.width(),logical_size.height()))
    if rect.width()<2 or rect.height()<2 or image.isNull():raise ValueError('请框选至少 2 × 2 的区域')
    sx,sy=pixel_scale(image,logical_size)
    left,top=max(0,math.floor(rect.left()*sx)),max(0,math.floor(rect.top()*sy))
    right,bottom=min(image.width(),math.ceil(rect.right()*sx)),min(image.height(),math.ceil(rect.bottom()*sy))
    return QRect(left,top,right-left,bottom-top)

def crop_selection(image,rect,logical_size):
    cropped=image.copy(selection_pixels(image,rect,logical_size));cropped.setDevicePixelRatio(1);return cropped
