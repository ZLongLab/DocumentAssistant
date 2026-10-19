"""Check real DWM captions, native window controls and the generated glass icon."""
import ctypes,json,os,struct,sys
from ctypes import wintypes
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QPoint,QSize,Qt
from PySide6.QtGui import QColor,QFont,QIcon,QImage,QPainter
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from document_assistant.gui import MainWindow,configure_app
from document_assistant.layout import apply_theme
from document_assistant.windows_identity import ICON_PATH
from document_assistant.window_chrome import caption_palette,colorref
from document_assistant.rules import DEFAULT_RULES
from document_assistant.service import scan_files,archive_batch
from tests.gui_wait import settle_search


def get_attribute(hwnd,attribute,ctype=wintypes.DWORD):
    dwm=ctypes.WinDLL('dwmapi',use_last_error=True);fn=dwm.DwmGetWindowAttribute
    fn.argtypes=[wintypes.HWND,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD];fn.restype=ctypes.c_long
    data=ctype();result=fn(hwnd,attribute,ctypes.byref(data),ctypes.sizeof(data))
    assert result>=0,(attribute,result)
    return data


def main():
    app=QApplication([]);configure_app(app)
    output=Path(os.environ['DOCUMENTASSISTANT_VERIFICATION']);output.mkdir(parents=True,exist_ok=True)
    errors=[];previous=sys.excepthook
    def hook(kind,value,trace):errors.append(str(value));previous(kind,value,trace)
    sys.excepthook=hook
    source=output/'示例来源';source.mkdir(exist_ok=True)
    for name,body in [('[示例] 实验报告.txt','实验报告\n实验目的：检查界面。\n实验结果：完成。'),
                      ('[示例] 课程笔记.txt','课程笔记\n知识点和课堂复习。'),
                      ('[示例] 项目计划.txt','项目计划\n进度安排和分工。')]:
        (source/name).write_text(body,encoding='utf-8')
    library=output/'示例文档库'
    if not (output/'prepared').exists():
        items,_=scan_files(list(source.iterdir()),DEFAULT_RULES,library)
        result=archive_batch(items,library);assert all(ok for _,ok,_ in result)
        (output/'prepared').write_text('generated examples',encoding='utf-8')
    window=MainWindow(output/'settings');window.set_library(library);window.tabs.setCurrentIndex(1)
    window.setWindowTitle('DocumentAssistant · 玻璃界面预览 · 全部为临时示例')
    window.page_subtitle.setText('临时示例 · 蓝黑标题栏与冰蓝玻璃图标')
    window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,True)
    window.resize(1280,760);window.move(80,80);window.show();window.raise_();window.activateWindow()
    settle_search(window);QTest.qWait(130)
    hwnd=int(window.winId());themes=[];geometry=window.geometry()
    try:
        for name in ('ocean','rose','starry'):
            apply_theme(window,name);QTest.qWait(50)
            palette=caption_palette(name)
            # These color attributes are documented setters, not readable state.
            actual=dict(window.window_chrome.last_result)
            assert all(actual.get(attribute,-1)==0 for attribute in (20,34,35,36)),actual
            assert get_attribute(hwnd,20).value==int(palette['dark'])
            assert window.geometry()==geometry,'Caption styling changed window geometry'
            themes.append({'theme':name,'caption':palette['caption'],'native_set_results':actual})
        api=ctypes.WinDLL('user32',use_last_error=True)
        api.GetWindowLongW.argtypes=[wintypes.HWND,ctypes.c_int];api.GetWindowLongW.restype=wintypes.LONG
        style=api.GetWindowLongW(hwnd,-16)&0xffffffff
        for flag in (0x00c00000,0x00040000,0x00020000,0x00010000):assert style&flag==flag
        window.showMaximized();QTest.qWait(90);assert window.isMaximized()
        window.showNormal();QTest.qWait(70);assert not window.isMaximized()
        window.showMinimized();QTest.qWait(60);assert window.isMinimized()
        window.showNormal();window.raise_();window.activateWindow();QTest.qWait(100)
        assert not window.isMinimized()
        assert window.window_chrome.last_result.get(35)==0
        window.grab().save(str(output/'client.png'))
        bounds=get_attribute(hwnd,9,wintypes.RECT)
        # This test window is on the primary display. Only its frame crop is saved.
        screen=window.screen();assert screen.geometry().topLeft()==QPoint(0,0)
        desktop=screen.grabWindow(0).toImage()
        frame=desktop.copy(bounds.left,bounds.top,bounds.right-bounds.left,bounds.bottom-bounds.top)
        sample=frame.pixelColor(round(frame.width()*.65),12)
        assert sample.red()<60 and sample.blue()<90,(sample.name(),'caption still light')
        frame.save(str(output/'window-with-titlebar.png'))
        icon=QIcon(str(ICON_PATH));assert not icon.isNull()
        sizes=[size.width() for size in icon.availableSizes()]
        assert {16,20,24,32,40,48,64,96,128,256}<=set(sizes),sizes
        header=struct.unpack('<HHH',ICON_PATH.read_bytes()[:6]);assert header==(0,1,10),header
        png=QImage(str(ICON_PATH.with_name('app-icon.png')))
        assert png.hasAlphaChannel() and png.pixelColor(0,0).alpha()==0
        sheet=QImage(900,210,QImage.Format.Format_ARGB32);sheet.fill(QColor('#101e2d'))
        p=QPainter(sheet);p.setPen(QColor('#dcecf7'));p.setFont(QFont('Segoe UI',10))
        x=28
        for size in (16,24,32,48,64,96,128):
            p.drawPixmap(x,22+(128-size)//2,icon.pixmap(size,size));p.drawText(x,184,str(size)+' px');x+=max(72,size+30)
        p.end();sheet.save(str(output/'icon-sizes.png'))
        assert not errors,errors
        report={'passed':True,'windows_build':sys.getwindowsversion().build,'themes':themes,
                'native_window_style':hex(style),'titlebar_sample':sample.name(),'icon':str(ICON_PATH),'sizes':sizes,
                'checks':['native caption color and text','theme switching without geometry changes',
                          'native resize/minimize/maximize styles retained','maximize/restore/minimize',
                          'dark titlebar actual screenshot','multi-size ICO and transparent PNG']}
        (output/'window-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2))
    finally:
        window.close();window.deleteLater();app.processEvents();sys.excepthook=previous


if __name__=='__main__':main()
