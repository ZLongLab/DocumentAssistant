"""Local screen selection, editable annotations, PNG export and tray lifecycle."""
import json
from .capture_focus import foreground_window, restore_foreground
import math
import os
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import (QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt,
                            QStandardPaths, QTimer, Signal, QSize)
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPolygonF, QIcon, QCursor, QPainterPath, QShortcut, QKeySequence
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMenu, QMessageBox, QPushButton, QScrollArea, QSystemTrayIcon, QVBoxLayout, QWidget, QFrame, QButtonGroup, QSizePolicy, QSpinBox)
from .capture_hotkey import GlobalHotkey, parse_hotkey
from .windows_identity import ICON_PATH
from .capture_style import CAPTURE_QSS
from .presentation import line_icon
from .ui_flow import FlowLayout


from .capture_pixels import crop_selection
from .capture_markup import draw_annotation, render_annotations


def save_png(image, directory, now=None):
    if image.isNull():raise ValueError('截图内容为空')
    directory=Path(directory).expanduser().resolve()
    directory.mkdir(parents=True,exist_ok=True)
    data=QByteArray();buffer=QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer,'PNG'):raise OSError('无法编码 PNG 图片')
    buffer.close()
    payload=bytes(data)
    stamp=(now or datetime.now()).strftime('%Y%m%d_%H%M%S')
    for index in range(10000):
        target=directory/f'截图_{stamp}{"_"+str(index) if index else ""}.png'
        try:handle=target.open('xb')
        except FileExistsError:continue
        try:
            with handle:
                handle.write(payload);handle.flush();os.fsync(handle.fileno())
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return target
    raise OSError('同一时间的截图文件过多，请更换保存目录')


def copy_image(image):
    clipboard=QApplication.clipboard()
    clipboard.setImage(image)
    actual=clipboard.image()
    if actual.isNull() or actual.size()!=image.size():
        raise OSError('剪贴板写入失败，请关闭占用剪贴板的程序后重试')


from .selection_overlay import SelectionOverlay
from .capture_canvas import AnnotationCanvas


class ColorDot(QPushButton):
    def __init__(self,color,title,parent):
        super().__init__('',parent)
        self.color=color
        self.setCheckable(True);self.setAutoDefault(False);self.setFixedSize(30,34)
        self.setToolTip(title);self.setAccessibleName(title)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        center=self.rect().center()
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(self.color));p.drawEllipse(center,9,9)
        if self.isChecked() or self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor(self.color),2));p.drawEllipse(center,13,13)
        p.end()


class PathLabel(QLabel):
    def __init__(self,path):
        super().__init__()
        self.full_text='保存到 '+str(path)
        self.setToolTip(str(path));self.setObjectName('capturePath')
        self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(80)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.setText(self.fontMetrics().elidedText(self.full_text,Qt.TextElideMode.ElideMiddle,self.width()))


class CaptureEditor(QDialog):
    def __init__(self,image,controller):
        super().__init__(None)
        self.controller=controller
        self.destination=Path(controller.settings['directory']).resolve()
        self.setWindowTitle('截图编辑 · DocumentAssistant')
        width=max(860,min(1180,image.width()+96))
        height=max(500,min(850,round(image.height()*min((width-64)/image.width(),1))+280))
        self.resize(width,height);self.setMinimumSize(560,400)
        self.setStyleSheet(CAPTURE_QSS)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        header=QFrame();header.setObjectName('captureHeader')
        head=QHBoxLayout(header);head.setContentsMargins(22,16,22,14);head.setSpacing(14)
        icon=QLabel();icon.setPixmap(line_icon('capture','#139d77').pixmap(30,30));head.addWidget(icon)
        heading=QVBoxLayout();heading.setSpacing(3)
        title=QLabel('截图编辑');title.setObjectName('captureTitle');heading.addWidget(title)
        meta=QLabel(f'框选完成  ·  {image.width()} × {image.height()} 像素  ·  PNG')
        meta.setObjectName('captureMeta');heading.addWidget(meta);head.addLayout(heading);head.addStretch()
        badge=QLabel('本地截图');badge.setObjectName('captureBadge');head.addWidget(badge)
        layout.addWidget(header)
        self.toolbar_frame=QWidget()
        toolbar=FlowLayout(self.toolbar_frame,6);toolbar.setContentsMargins(20,8,20,8)
        layout.addWidget(self.toolbar_frame)
        self.tools=QComboBox(self);self.tools.hide()
        group=QFrame();group.setObjectName('toolGroup')
        group_layout=QHBoxLayout(group);group_layout.setContentsMargins(4,4,4,4);group_layout.setSpacing(3)
        self.tool_buttons={};self.tool_group=QButtonGroup(self)
        for index,(name,key,icon_name) in enumerate([('查看','view','cursor'),('选择','select','cursor'),('矩形','rectangle','rectangle'),('箭头','arrow','arrow'),('文字','text','text'),('遮挡','mask','rectangle')]):
            self.tools.addItem(name,key)
            button=QPushButton(name);button.setObjectName('tool');button.setCheckable(True);button.setAutoDefault(False)
            button.setIcon(line_icon(icon_name,'#4b6c5a'));button.setIconSize(QSize(17,17))
            button.setToolTip(name+'工具');self.tool_group.addButton(button,index)
            button.clicked.connect(lambda checked=False,i=index:self.tools.setCurrentIndex(i))
            self.tool_buttons[key]=button;group_layout.addWidget(button)
        toolbar.addWidget(group)
        options=QWidget();option_row=QHBoxLayout(options);option_row.setContentsMargins(0,0,0,0);option_row.setSpacing(4)
        divider=QFrame();divider.setFrameShape(QFrame.Shape.VLine);divider.setStyleSheet('color:#dce5df;');divider.setFixedHeight(26);option_row.addWidget(divider)
        self.colors=QComboBox(self);self.colors.hide();self.color_group=QButtonGroup(self);self.color_buttons=[]
        for index,(name,color) in enumerate([('红色','#e34f45'),('橙色','#ec9b21'),('蓝色','#377fde'),('绿色','#24825c')]):
            self.colors.addItem(name,color)
            dot=ColorDot(color,name,self);self.color_group.addButton(dot,index)
            dot.clicked.connect(lambda checked=False,i=index:self.colors.setCurrentIndex(i))
            self.color_buttons.append(dot);option_row.addWidget(dot)
        self.width_spin=QSpinBox();self.width_spin.setRange(1,12);self.width_spin.setValue(3);self.width_spin.setPrefix('线 ')
        self.size_spin=QSpinBox();self.size_spin.setRange(12,96);self.size_spin.setValue(22);self.size_spin.setPrefix('字 ')
        for spin in (self.width_spin,self.size_spin):spin.setFixedWidth(70);option_row.addWidget(spin)
        toolbar.addWidget(options)
        zoom_group=QWidget();zoom_row=QHBoxLayout(zoom_group);zoom_row.setContentsMargins(0,0,0,0);zoom_row.setSpacing(4)
        self.zoom_label=QLabel('100%');zoom_row.addWidget(self.zoom_label)
        self.fit_button=QPushButton('适应');self.actual_button=QPushButton('100%')
        for zoom_button in (self.fit_button,self.actual_button):
            zoom_button.setAutoDefault(False);zoom_button.setObjectName('zoomButton');zoom_row.addWidget(zoom_button)
        self.undo_button=QPushButton('撤销');self.undo_button.setEnabled(False);self.undo_button.setAutoDefault(False)
        self.undo_button.setIcon(line_icon('undo','#6b8272'));self.undo_button.setToolTip('撤销上一个标注 · Ctrl+Z')
        zoom_row.addWidget(self.undo_button)
        self.redo_button=QPushButton('重做');self.redo_button.setAutoDefault(False);self.redo_button.setEnabled(False)
        zoom_row.addWidget(self.redo_button);toolbar.addWidget(zoom_group)
        edit_group=QWidget();self.edit_group=edit_group;edit_row=QHBoxLayout(edit_group);edit_row.setContentsMargins(0,0,0,0);edit_row.setSpacing(4)
        self.text_button=QPushButton('改文字');self.delete_button=QPushButton('删除标注')
        for button in (self.text_button,self.delete_button):button.setAutoDefault(False);button.setEnabled(False);edit_row.addWidget(button)
        toolbar.addWidget(edit_group)
        self.canvas=AnnotationCanvas(image)
        body=QHBoxLayout();body.setContentsMargins(20,0,20,0)
        scroll=QScrollArea();scroll.setFrameShape(QFrame.Shape.NoFrame);scroll.setWidgetResizable(True)
        scroll.viewport().setAutoFillBackground(False);scroll.setWidget(self.canvas);body.addWidget(scroll)
        layout.addLayout(body,1)
        self.tools.currentIndexChanged.connect(self.set_tool)
        self.colors.currentIndexChanged.connect(self.set_color)
        self.undo_button.clicked.connect(self.canvas.undo)
        self.redo_button.clicked.connect(self.canvas.redo)
        self.delete_button.clicked.connect(self.canvas.delete_selected)
        self.text_button.clicked.connect(self.canvas.edit_text)
        self.canvas.selection_changed.connect(self.selection_changed)
        self.width_spin.valueChanged.connect(lambda value:self.canvas.apply_style(width=value))
        self.size_spin.valueChanged.connect(lambda value:self.canvas.apply_style(size=value))
        self.canvas.changed.connect(self.content_changed)
        self.canvas.zoom_changed.connect(lambda value:self.zoom_label.setText(f'{value:.0%}'))
        self.canvas.setToolTip('滚轮缩放；查看工具拖动平移；标注时按住鼠标中键平移')
        self.fit_button.clicked.connect(lambda:self.canvas.set_zoom())
        self.actual_button.clicked.connect(lambda:self.canvas.set_zoom(1.))
        self.saved_image=None
        self.saved_path=None
        self.undo_shortcut=QShortcut(QKeySequence('Ctrl+Z'),self);self.undo_shortcut.activated.connect(self.canvas.undo)
        self.redo_shortcut=QShortcut(QKeySequence('Ctrl+Y'),self);self.redo_shortcut.activated.connect(self.canvas.redo)
        self.set_tool();self.set_color()
        footer=QHBoxLayout();footer.setContentsMargins(22,16,22,18);footer.setSpacing(10)
        destination=QVBoxLayout();destination.setSpacing(5)
        self.path_label=PathLabel(controller.settings['directory']);self.path_label.setParent(self);self.path_label.hide()
        hint=QLabel('Enter 复制  ·  Esc 取消');hint.setObjectName('captureHint');destination.addWidget(hint)
        footer.addLayout(destination,1)
        desktop=Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)).resolve()
        save_title='保存到桌面' if Path(controller.settings['directory']).resolve()==desktop else '保存图片'
        self.save_button=QPushButton(save_title);self.save_button.setObjectName('saveCapture');self.save_button.setAutoDefault(False)
        self.save_button.setToolTip('保存 PNG 到 '+controller.settings['directory'])
        self.copy_button=QPushButton('仅复制');self.copy_button.setObjectName('copyCapture')
        self.copy_button.setIcon(line_icon('copy','#ffffff'));self.copy_button.setDefault(True)
        cancel=QPushButton('取消');cancel.setObjectName('cancelCapture');cancel.setAutoDefault(False)
        self.save_button.clicked.connect(self.save);self.copy_button.clicked.connect(self.copy);cancel.clicked.connect(self.reject)
        for widget in (cancel,self.save_button,self.copy_button):footer.addWidget(widget)
        self.message=QLabel();self.message.setObjectName('captureError');self.message.setWordWrap(True);self.message.hide()
        self.message_container=QHBoxLayout();self.message_container.setContentsMargins(20,10,20,0)
        self.message_container.addWidget(self.message);layout.addLayout(self.message_container)
        layout.addLayout(footer)
        self.copy_button.setFocus()

    def set_tool(self,*_):
        self.canvas.start=self.canvas.end=None;self.canvas.tool=self.tools.currentData()
        if self.canvas.tool!='select':self.canvas.selected_index=None;self.selection_changed()
        for key,button in self.tool_buttons.items():button.setChecked(key==self.canvas.tool)
        self.canvas.update()

    def set_color(self,*_):
        self.canvas.apply_style(color=self.colors.currentData())
        for index,button in enumerate(self.color_buttons):button.setChecked(index==self.colors.currentIndex());button.update()

    def selection_changed(self):
        index=self.canvas.selected_index
        self.edit_group.setVisible(index is not None)
        self.delete_button.setEnabled(index is not None)
        self.text_button.setEnabled(index is not None and self.canvas.marks[index][0]=='text')
        if index is not None:
            from .capture_markup import style_of
            mark=self.canvas.marks[index];style=style_of(mark)
            for spin,value in ((self.width_spin,style.get('width',3)),(self.size_spin,style.get('size',22))):
                blocked=spin.blockSignals(True);spin.setValue(value);spin.blockSignals(blocked)
            self.canvas.line_width=self.width_spin.value();self.canvas.text_size=self.size_spin.value()
            self.canvas.color=mark[4]
            blocked=self.colors.blockSignals(True);self.colors.setCurrentIndex(self.colors.findData(mark[4]));self.colors.blockSignals(blocked)
            for i,button in enumerate(self.color_buttons):button.setChecked(i==self.colors.currentIndex());button.update()

    def content_changed(self):
        self.undo_button.setEnabled(bool(self.canvas.marks) or bool(self.canvas.history))
        self.redo_button.setEnabled(bool(self.canvas.future))
        self.save_button.setEnabled(True)
        self.message.hide()

    def show_error(self,text):
        self.message.setText(text);self.message.show()

    def save(self):
        image=self.canvas.rendered()
        try:
            if self.saved_image is not None and image==self.saved_image and self.saved_path and self.saved_path.is_file():
                path=self.saved_path
            else:
                path=save_png(image,self.destination)
                self.saved_image=image.copy();self.saved_path=path
        except Exception as exc:self.show_error('保存失败，可重试或仅复制：'+str(exc));return
        self.controller.last_saved=path
        try:copy_image(image)
        except Exception as exc:
            self.show_error(f'文件已保存到 {path}；{exc}')
            self.save_button.setEnabled(True)
            self.controller.notify('截图已保存，但复制失败',str(path))
            return
        self.controller.notify('截图已保存并复制',str(path));self.accept()

    def copy(self):
        try:copy_image(self.canvas.rendered())
        except Exception as exc:self.show_error(str(exc));return
        self.controller.notify('截图已复制','可以粘贴到 Word 或聊天窗口');self.accept()


class CaptureSettingsDialog(QDialog):
    def __init__(self,controller):
        super().__init__(controller.window)
        self.controller=controller
        self.setWindowTitle('截图设置');self.resize(620,300);self.setStyleSheet(CAPTURE_QSS)
        layout=QVBoxLayout(self);form=QFormLayout()
        self.hotkey=QLineEdit(controller.settings['hotkey'])
        self.directory=QLineEdit(controller.settings['directory'])
        directory_row=QHBoxLayout();directory_row.addWidget(self.directory)
        choose=QPushButton('选择文件夹');directory_row.addWidget(choose)
        choose.clicked.connect(self.choose)
        form.addRow('截图快捷键',self.hotkey);form.addRow('保存到',directory_row)
        layout.addLayout(form)
        description=QLabel('例如 Alt+S，只需两个键。关闭主窗口后截图功能在托盘运行；退出程序后快捷键释放。\n多屏可在任一屏幕框选；一次框选在一块屏幕内完成。')
        description.setWordWrap(True);layout.addWidget(description)
        self.error=QLabel();self.error.setWordWrap(True);layout.addWidget(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def choose(self):
        path=QFileDialog.getExistingDirectory(self,'选择截图保存目录',self.directory.text())
        if path:self.directory.setText(path)

    def save(self):
        try:self.controller.configure(self.hotkey.text(),self.directory.text())
        except Exception as exc:self.error.setText(str(exc));return
        self.accept()


class CaptureController:
    def __init__(self,window,activate=True):
        self.window=window;self.app=QApplication.instance()
        self.path=window.home/'screenshot.json'
        desktop=QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
        self.settings={'hotkey':'Alt+S','directory':desktop or str(Path.home()/'Desktop')}
        try:
            if self.path.exists():
                saved=json.loads(self.path.read_text(encoding='utf-8'))
                hotkey,_,_=parse_hotkey(saved['hotkey'])
                directory=saved['directory']
                if not isinstance(directory,str) or not Path(directory).is_absolute():raise ValueError('保存目录需要完整路径')
                self.settings={'hotkey':hotkey,'directory':directory}
        except Exception as exc:window.statusBar().showMessage('截图设置读取失败，使用默认设置：'+str(exc))
        self.update_entry()
        self.hotkey=GlobalHotkey(self.app,lambda:self.begin(from_hotkey=True))
        self.overlays=[];self.editor=None;self.capturing=False;self.restore_main=False
        self.exiting=False;self.exit_pending=False;self.stopped=False;self.last_saved=None
        self.from_hotkey=False;self.previous_foreground=None
        self.recording=None;self.record_controls=None;self.video_stop=None;self.last_video=None
        self.video_countdown=QTimer(window);self.video_countdown.setInterval(1000)
        self.video_countdown.timeout.connect(self.countdown_video)
        self.tray=None
        if activate:
            if QSystemTrayIcon.isSystemTrayAvailable():
                self.tray=QSystemTrayIcon(QIcon(str(ICON_PATH)),window)
                self.tray.setToolTip('DocumentAssistant · 截图 '+self.settings['hotkey'])
                menu=QMenu(window)
                menu.addAction('框选截图',self.begin);menu.addAction('打开文件管理',self.show_main)
                self.video_stop=menu.addAction('停止视频录制',self.stop_recording);self.video_stop.setEnabled(False)
                menu.addAction('截图设置',self.show_settings);menu.addAction('打开截图保存目录',self.open_directory)
                menu.addAction('打开最近保存的截图',self.open_last)
                menu.addAction('打开最近保存的视频',self.open_last_video)
                menu.addSeparator();menu.addAction('退出程序',self.exit)
                self.tray.setContextMenu(menu)
                self.tray.activated.connect(lambda reason:self.show_main() if reason==QSystemTrayIcon.ActivationReason.DoubleClick else None)
                self.tray.show();self.app.setQuitOnLastWindowClosed(False)
            try:self.hotkey.commit(self.hotkey.prepare(self.settings['hotkey']))
            except ValueError as exc:
                window.statusBar().showMessage(str(exc))
                QTimer.singleShot(500,lambda message=str(exc):self.notify('截图快捷键未启用',message))

        self.update_entry()

    def configure(self,hotkey,directory):
        if self.recording and not self.recording.done:raise ValueError('请先完成或取消当前录制，再修改截图设置')
        path=Path(directory).expanduser()
        if not directory.strip() or not path.is_absolute():raise ValueError('请填写完整的截图保存目录')
        if path.exists() and not path.is_dir():raise ValueError('保存位置必须是文件夹')
        canonical,_,_=parse_hotkey(hotkey)
        prepared=None if self.hotkey.ident is not None and canonical==self.hotkey.text else self.hotkey.prepare(canonical)
        data={'hotkey':canonical,'directory':str(path.resolve())}
        try:
            temporary=self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
            temporary.replace(self.path)
        except Exception:
            if prepared:self.hotkey.rollback(prepared)
            raise
        if prepared:self.hotkey.commit(prepared)
        self.settings=data
        self.update_entry()
        if self.tray:self.tray.setToolTip('DocumentAssistant · 截图 '+data['hotkey'])

    def update_entry(self):
        key=self.settings['hotkey']
        active=hasattr(self,'hotkey') and self.hotkey.ident is not None
        self.window.screenshot_button.setText(('框选截图  '+key if len(key)<=7 else '框选截图') if active else '框选截图 · 热键未启用')
        self.window.screenshot_button.setToolTip(('截图快捷键 '+key if active else key+' 未启用，可能被占用；仍可点击截图')+'；框选界面可切换视频，录制时再按热键停止')

    def show_settings(self):
        if self.recording and not self.recording.done:
            self.notify('正在录制','请先停止或取消录制，再修改截图设置');return
        CaptureSettingsDialog(self).exec()

    def notify(self,title,text):
        self.window.statusBar().showMessage(title+'：'+text,10000)
        if self.tray:self.tray.showMessage(title,text,QSystemTrayIcon.MessageIcon.Information,3500)

    def show_main(self):
        if self.capturing:return
        self.window.showNormal();self.window.raise_();self.window.activateWindow()

    def begin(self,*_,from_hotkey=False):
        if getattr(self,'recording',None) and not self.recording.done:
            self.stop_recording();return
        if self.capturing or self.exiting or self.window.closing:return
        if QApplication.activeModalWidget():
            self.notify('请先关闭对话框','关闭当前设置或确认窗口后再截图');return
        self.capturing=True
        self.from_hotkey=from_hotkey
        self.previous_foreground=foreground_window() if from_hotkey else None
        self.restore_main=self.window.isVisible() and not self.window.isMinimized()
        self.window.hide()
        QTimer.singleShot(180,self.snapshot)

    def snapshot(self):
        if self.exiting or not self.capturing:return
        try:
            frames=[(screen,screen.grabWindow(0).toImage()) for screen in self.app.screens()]
            if not frames or any(image.isNull() for _,image in frames):raise OSError('无法读取屏幕画面')
            for screen,image in frames:
                overlay=SelectionOverlay(screen,image)
                overlay.stop_key=self.hotkey.text if self.hotkey.ident is not None else '托盘菜单'
                overlay.refresh_toolbar()
                overlay.video_selected.connect(lambda rect,target=screen:self.begin_video(target,rect))
                overlay.mode_changed.connect(self.change_capture_mode)
                overlay.selected.connect(lambda image,target=screen:self.selected(image,target));overlay.cancelled.connect(self.cancel)
                self.overlays.append(overlay)
            # Every snapshot is taken before any selection overlay becomes visible.
            for overlay in self.overlays:overlay.show();overlay.raise_()
            active=next((o for o in self.overlays if o.geometry().contains(QCursor.pos())),self.overlays[0])
            active.activateWindow();active.setFocus()
        except Exception as exc:self.notify('截图失败',str(exc));self.cancel()

    def close_overlays(self):
        overlays,self.overlays=self.overlays,[]
        for overlay in overlays:overlay.close();overlay.deleteLater()

    def selected(self,image,screen=None):
        self.close_overlays()
        self.editor=CaptureEditor(image,self)
        self.editor.finished.connect(self.finished)
        if screen:
            area=screen.availableGeometry()
            self.editor.resize(min(self.editor.width(),area.width()-32),min(self.editor.height(),area.height()-48))
            self.editor.move(area.x()+(area.width()-self.editor.width())//2,area.y()+(area.height()-self.editor.height())//2)
        self.editor.show();self.editor.raise_();self.editor.activateWindow()

    def change_capture_mode(self,mode):
        for overlay in self.overlays:overlay.set_mode(mode)

    def begin_video(self,screen,rect):
        if self.recording:return
        try:
            from .video_recording import RegionRecorder
            from .video_ui import RecordingControls,controls_position
            self.recording=RegionRecorder(screen,rect,self.window.home,self.window)
            self.recording.started.connect(self.recording_started)
            self.recording.progress.connect(self.recording_progress)
            self.recording.completed.connect(self.video_completed)
            self.recording.failed.connect(self.video_failed)
            key=self.hotkey.text if self.hotkey.ident is not None else '托盘菜单'
            self.record_controls=RecordingControls(key)
            self.record_controls.stop_requested.connect(self.stop_recording)
            self.record_controls.cancel_requested.connect(self.cancel)
            region=rect.toAlignedRect().translated(screen.geometry().topLeft())
            point=controls_position(screen.availableGeometry(),region,self.record_controls.size())
            # Full-screen recording uses the hotkey/tray; no control panel is recorded.
            self.record_controls_position=point
            if point is None and self.hotkey.ident is None and not self.tray:
                raise ValueError('全屏录制需要启用截图热键，或使用系统托盘停止录制')
            if point is not None:self.record_controls.move(point)
            self.countdown_remaining=3
            for overlay in self.overlays:
                overlay.lock_selection()
                overlay.confirm_button.setText('3 秒后开始 · Esc 取消')
                if overlay.start is not None:overlay.position_actions()
            if self.video_stop:self.video_stop.setEnabled(True)
            self.video_countdown.start()
        except Exception as exc:self.video_failed(str(exc))

    def countdown_video(self):
        if not self.recording or self.exiting:self.video_countdown.stop();return
        self.countdown_remaining-=1
        for overlay in self.overlays:
            overlay.confirm_button.setText(f'{self.countdown_remaining} 秒后开始 · Esc 取消')
            if overlay.start is not None:overlay.position_actions()
        if self.countdown_remaining<=0:
            self.video_countdown.stop();self.close_overlays()
            if self.record_controls_position is not None:self.record_controls.show()
            target=self.previous_foreground
            if self.from_hotkey:restore_foreground(target)
            recording=self.recording
            QTimer.singleShot(250,lambda:recording.start() if self.recording is recording and self.capturing else None)

    def recording_started(self):
        if self.record_controls:self.record_controls.started()
        if self.tray:self.tray.setToolTip('正在录制视频 · '+self.hotkey.text+' 停止')

    def recording_progress(self,millis):
        if self.record_controls:self.record_controls.progress(millis)

    def stop_recording(self,*_):
        if not self.recording or self.recording.done:return
        if self.video_countdown.isActive() or self.recording.path is None:self.cancel();return
        if self.record_controls:self.record_controls.stopping()
        if self.video_stop:self.video_stop.setEnabled(False)
        self.recording.stop()

    def video_completed(self,path):
        if self.exiting:
            self.recording.keep_file=True;self.finished();return
        from .video_ui import VideoPreview
        if self.record_controls:self.record_controls.hide()
        if self.video_stop:self.video_stop.setEnabled(False)
        try:self.editor=VideoPreview(path,self,self.recording.interruption)
        except Exception as exc:
            self.recording.keep_file=True;self.video_failed('无法打开预览：'+str(exc));return
        self.editor.finished.connect(self.finished)
        try:area=self.recording.screen.availableGeometry()
        except RuntimeError:area=self.app.primaryScreen().availableGeometry()
        self.editor.resize(min(self.editor.width(),area.width()-32),min(self.editor.height(),area.height()-48))
        self.editor.move(area.x()+(area.width()-self.editor.width())//2,area.y()+(area.height()-self.editor.height())//2)
        self.editor.show();self.editor.raise_();self.editor.activateWindow()

    def video_failed(self,message):
        if self.recording:
            self.recording.keep_file=True
            if self.recording.path and self.recording.path.is_file():
                message+='；临时视频已保留（可能不完整）：'+str(self.recording.path)
        self.close_overlays();self.finished();self.notify('录制失败',message)

    def finished(self,*_):
        editor,self.editor=self.editor,None
        if editor:editor.deleteLater()
        if getattr(self,'recording',None):
            self.video_countdown.stop()
            recording,self.recording=self.recording,None
            recording.quiesce()
            def cleanup():
                try:recording.discard()
                except OSError as exc:self.notify('临时视频已保留',str(recording.path)+'；'+str(exc))
                recording.deleteLater()
            QTimer.singleShot(250,cleanup)
        if getattr(self,'record_controls',None):self.record_controls.close();self.record_controls.deleteLater();self.record_controls=None
        if getattr(self,'video_stop',None):self.video_stop.setEnabled(False)
        if getattr(self,'tray',None):self.tray.setToolTip('DocumentAssistant · 截图 '+self.settings['hotkey'])
        self.capturing=False
        if self.restore_main and not self.exiting:
            if self.from_hotkey:
                self.window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating,True)
                self.window.show()
                self.window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating,False)
            else:self.show_main()
        if self.from_hotkey and not self.exiting:
            target=self.previous_foreground
            QTimer.singleShot(0,lambda:restore_foreground(target))

    def cancel(self):
        if self.recording and self.recording.frames and not self.recording.done:
            self.stop_recording();return
        self.close_overlays();self.finished()

    def open_directory(self):
        path=Path(self.settings['directory'])
        try:path.mkdir(parents=True,exist_ok=True);self.window.open_path(path)
        except OSError as exc:self.notify('目录无法打开',str(exc))

    def open_last(self):
        if self.last_saved and self.last_saved.is_file():self.window.open_path(self.last_saved)
        else:self.notify('没有可打开的截图','本次运行尚未保存截图，或图片已经被移动')

    def open_last_video(self):
        if self.last_video and self.last_video.is_file():self.window.open_path(self.last_video)
        else:self.notify('没有可打开的视频','本次运行尚未保存视频，或视频已经被移动')

    def exit(self):
        if self.capturing:
            self.notify('请先完成截图或录制','录制时按截图热键停止，保存或关闭预览后再退出');return
        self.exiting=True
        if self.window.worker and not self.exit_pending:
            self.exit_pending=True
            self.window.worker.finished.connect(lambda:QTimer.singleShot(0,self.window.close))
        self.window.close()

    def shutdown(self):
        if self.stopped:return
        self.stopped=True;self.exiting=True
        self.close_overlays();self.hotkey.shutdown()
        self.video_countdown.stop()
        if self.recording:
            self.recording.keep_file=True
            self.recording.timer.stop();self.recording.stop()
        if self.record_controls:self.record_controls.close()
        if self.editor:
            if hasattr(self.editor,'release_player'):
                self.editor.release_player();QDialog.reject(self.editor)
            else:self.editor.reject()
        if self.tray:self.tray.hide()
