import bootstrap
import sys
import math
import time
import sqlite3
from pathlib import Path
from datetime import datetime
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, QEvent, QRect, QSize
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtGui import QColor, QPainter, QPen, QFont, QImage, QPixmap, QIcon, QLinearGradient, QShortcut, QKeySequence
from PyQt6.QtWidgets import (QApplication, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QMessageBox, QLineEdit, QDialog, QFormLayout, QDoubleSpinBox, QGraphicsDropShadowEffect,
    QScrollArea, QSizePolicy, QSpinBox, QComboBox)
from storage import Store, ROOT, DATA
from vision import Worker

MINT = '#8cf5d1'
MUTED = '#73918c'
STYLE = '''
QWidget {color:#d8e8e3; font-family:'Microsoft YaHei UI'; font-size:12px;}
QWidget#shell {background:#080f12; border:1px solid #28453e; border-radius:14px;}
QFrame#topbar {background:#0b1518; border-bottom:1px solid #223b35; border-top-left-radius:14px; border-top-right-radius:14px;}
QFrame#sidebar {background:#0c171a; border:1px solid #203931; border-radius:10px;}
QFrame#dock {background:rgba(12,25,28,245); border:1px solid #3a6055; border-radius:15px;}
QFrame#card {background:#111f22; border:1px solid #223b35; border-radius:8px;}
QLabel {border:none; background:transparent;}
QPushButton {background:#132326; border:1px solid #2a4540; border-radius:7px; padding:8px 13px; color:#a7c2ba;}
QPushButton:hover {background:#203b35; color:#b5ffe4; border-color:#589c86;}
QPushButton:pressed {background:#345349;}
QPushButton:checked {background:#19372d; border-color:#5c9e80; color:#b7ffdf;}
QPushButton:disabled {color:#4f6661; background:#101b1e; border-color:#1a2b27;}
QPushButton[primary='true'] {background:#9af3d0; color:#0b2820; border:1px solid #adffdf; font-weight:600;}
QPushButton[role='blue'] {background:#112331; color:#9bcefb; border-color:#284658;}
QPushButton[role='blue']:hover {background:#1c3548; border-color:#5588af;}
QPushButton[role='red'] {background:#2b191e; color:#ffa8aa; border-color:#64323b;}
QPushButton[role='red']:hover {background:#48232a; border-color:#ab5261;}
QPushButton[nav='true'] {background:transparent; border:0; color:#7f9d95; padding:11px 18px; border-radius:0;}
QPushButton[nav='true']:checked {color:#adffe0; background:#122822; border-bottom:2px solid #95f3ce;}
QPushButton#windowButton {border:0; background:transparent; border-radius:0; font-size:16px; padding:0;}
QPushButton#closeButton {border:0; background:transparent; font-size:20px; padding:0;}
QPushButton#closeButton:hover {background:#9e3c45; color:white;}
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {background:#081416; border:1px solid #2b4941; border-radius:6px; padding:6px; selection-background-color:#31745e;}
QComboBox#cameraSelect {background:#112331; color:#9bcefb; border-color:#284658; min-height:25px; padding:5px 9px;}
QComboBox#cameraSelect:hover {border-color:#5588af; background:#172e3e;}
QComboBox::drop-down {border:0; width:22px;}
QComboBox QAbstractItemView {background:#102127; color:#c0dbd0; border:1px solid #355b4d; selection-background-color:#214b3e; padding:4px; outline:0;}
QTableWidget {background:#0d191c; alternate-background-color:#102023; border:1px solid #223c35; gridline-color:#1a302b; selection-background-color:#234c3d;}
QHeaderView::section {background:#152a28; border:0; border-bottom:1px solid #2d4d42; padding:10px; color:#91b6a7;}
QScrollArea {background:transparent; border:0;}
QScrollBar:vertical {background:#101d20; width:5px;}
QScrollBar::handle:vertical {background:#34594c; border-radius:2px; min-height:24px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
QDialog {background:#0c191c;}
QToolTip {background:#17332c; color:#ceffeb; border:1px solid #537f6f; padding:6px;}
'''


def label(text, size=12, color='#d8e8e3', bold=False):
    widget = QLabel(text)
    widget.setStyleSheet(f'color:{color}; font-size:{size}px; font-weight:{600 if bold else 400};')
    return widget


class IconButton(QPushButton):
    def setText(self,text):
        icons = [('退出全屏','exitfullscreen'),('全屏','fullscreen'),('暂停','pause'),('开始','play'),('继续','play'),('重新','play'),('打卡','checkin'),('面部网格','mesh'),('人体骨架','pose'),('镜像','mirror'),('截图','snapshot'),('摄像头','camera'),('当前画面','camera'),('图片 / 视频','folder'),('照片','photo'),('录入学生','adduser'),('删除','trash'),('编辑','edit'),('导出','export'),('保存','save'),('实时检测','scan'),('学生档案','users'),('识别记录','history')]
        name = next((icon for title,icon in icons if title in text),None)
        name = {'−':'minimize','□':'maximize','×':'close','⛶':'fullscreen'}.get(text,name)
        clean = text.lstrip('◉＋▶▣◎⛶⇋Ⅱ✓−□× ')
        super().setText(clean)
        if name:
            role = self.property('role') or 'dark'
            self.setIcon(QIcon(str(ROOT / 'assets/icons' / f'{name}-{role}.svg')))
            self.setIconSize(QSize(17,17))


def button(text, callback, primary=False):
    b = IconButton()
    role = 'red' if any(t in text for t in ['删除','×']) else 'green' if primary else 'blue' if any(t in text for t in ['摄像头','图片 / 视频','照片','导出','录入学生','当前画面']) else 'dark'
    b.setProperty('role',role)
    b.setText(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setProperty('primary', primary)
    b.clicked.connect(callback)
    return b


class Topbar(QFrame):
    def __init__(self, window):
        super().__init__()
        self.owner_window = window
        self.setObjectName('topbar')
        self.setFixedHeight(54)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 6, 0)
        layout.setSpacing(8)
        logo = QLabel()
        logo.setPixmap(QPixmap(str(ROOT / 'assets/logo.png')).scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        logo.setFixedWidth(34)
        layout.addWidget(logo)
        layout.addWidget(label('家和丨', 20, '#e1f8ec', True))
        layout.addStretch(1)
        self.tabs = []
        for index, title in enumerate(['实时检测', '学生档案', '识别记录']):
            b = button(title, lambda checked=False, i=index: window.change_tab(i))
            b.setProperty('nav', True)
            b.setCheckable(True)
            b.setChecked(index == 0)
            self.tabs.append(b)
            layout.addWidget(b)
        layout.addStretch(1)
        self.clock = label('', 11, MUTED)
        layout.addWidget(self.clock)
        layout.addSpacing(12)
        for text, callback, name in [('⛶', window.toggle_fullscreen, 'windowButton'), ('−', window.showMinimized, 'windowButton'), ('□', window.toggle_max, 'windowButton'), ('×', window.close, 'closeButton')]:
            b = button(text, callback)
            b.setObjectName(name)
            b.setFixedSize(36, 40)
            layout.addWidget(b)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.owner_window.windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.owner_window.toggle_max()


class VideoCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(400, 350)
        self.image = None
        self.stats = {}
        self.phase = 0
        self.paint_times = []
        self.render_fps = 0.
        self.telemetry = {}
        self.mesh_enabled = True
        self.pose_enabled = True
        self.box_motion = {}
        self.animation_until = 0.
        self.dock = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(16)

    def animate(self):
        if self.image is None:
            self.phase += .025
            self.update()
        elif time.monotonic()<self.animation_until:
            self.update()

    def set_frame(self, image, stats):
        now = time.monotonic()
        boxes = {('face',f.get('track_id',i)):f['box'] for i,f in enumerate(stats.get('faces',[]))}
        boxes.update({('person',t['track_id']):t['box'] for t in stats.get('person_tracks',[])})
        motions = {}
        for key,target in boxes.items():
            current = self.display_box(key,target)
            motions[key] = (current,tuple(target),now)
        self.box_motion = motions
        self.animation_until = now+.09
        self.image = image
        self.stats = stats
        self.update()

    def display_box(self,key,fallback):
        if key not in self.box_motion:
            return tuple(fallback)
        start,end,timestamp = self.box_motion[key]
        alpha = min(1.,max(0.,(time.monotonic()-timestamp)/.085))
        alpha = alpha*alpha*(3-2*alpha)
        return tuple(a+(b-a)*alpha for a,b in zip(start,end))

    def resizeEvent(self, event):
        if self.dock:
            if hasattr(self,'reflow_dock'):
                self.reflow_dock(self.width())
            self.dock.adjustSize()
            self.dock.move((self.width()-self.dock.width())//2, self.height()-self.dock.height()-18)
        super().resizeEvent(event)

    def paintEvent(self, event):
        now = time.perf_counter()
        self.paint_times = [t for t in self.paint_times if now-t < 1.5]
        self.paint_times.append(now)
        self.render_fps = (len(self.paint_times)-1)/max(now-self.paint_times[0],.001) if len(self.paint_times)>1 else 0.
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor('#081215'))
        p.setPen(QPen(QColor('#112226'), 1))
        for x in range(0, w, 36):
            p.drawLine(x, 0, x, h)
        for y in range(0, h, 36):
            p.drawLine(0, y, w, y)
        if self.image is not None:
            ih, iw = self.image.shape[:2]
            scale = min(w/iw, h/ih)
            dw, dh = iw*scale, ih*scale
            ox, oy = (w-dw)/2, (h-dh)/2
            rgb = cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB)
            qimage = QImage(rgb.data, iw, ih, rgb.strides[0], QImage.Format.Format_RGB888)
            p.drawImage(QRectF(ox, oy, dw, dh), qimage)
            for track in self.stats.get('person_tracks', []):
                box = self.display_box(('person',track['track_id']),track['box'])
                x, y, bw, bh = box
                r = QRectF(ox+x*scale, oy+y*scale, bw*scale, bh*scale)
                p.setPen(QPen(QColor(135, 198, 207, 130), 1, Qt.PenStyle.DashLine))
                p.drawRect(r)
                p.setFont(QFont('Consolas',9))
                p.drawText(QPointF(r.left()+5,r.bottom()-8),f"PERSON / P{track['track_id']:03d}")
            if self.mesh_enabled:
                p.setPen(QPen(QColor(129,237,206,85),.6))
                for mesh in self.stats.get('mesh',[]):
                    for a,b in self.stats.get('mesh_edges',[]):
                        if a<len(mesh) and b<len(mesh):
                            p.drawLine(QPointF(ox+mesh[a][0]*scale,oy+mesh[a][1]*scale),QPointF(ox+mesh[b][0]*scale,oy+mesh[b][1]*scale))
            if self.pose_enabled:
                for pose in self.stats.get('poses',[]):
                    p.setPen(QPen(QColor(123,219,245,190),2))
                    for a,b in self.stats.get('pose_edges',[]):
                        if a<len(pose) and b<len(pose) and pose[a][2]>.5 and pose[b][2]>.5:
                            p.drawLine(QPointF(ox+pose[a][0]*scale,oy+pose[a][1]*scale),QPointF(ox+pose[b][0]*scale,oy+pose[b][1]*scale))
                    p.setBrush(QColor('#d2faff'))
                    p.setPen(QPen(QColor('#518f9c'),1))
                    for px,py,visibility in pose:
                        if visibility>.5:
                            p.drawEllipse(QPointF(ox+px*scale,oy+py*scale),2.6,2.6)
            for item in self.stats.get('faces', []):
                x,y,bw,bh = self.display_box(('face',item.get('track_id',0)),item['box'])
                r = QRectF(ox+x*scale, oy+y*scale, bw*scale, bh*scale)
                color = QColor(MINT if item['sid'] else '#ffc885')
                self.draw_brackets(p, r, color, max(12, min(30, bw*scale*.2)))
                for lx, ly in item['landmarks']:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(color.red(), color.green(), color.blue(), 150))
                    p.drawEllipse(QPointF(ox+lx*scale, oy+ly*scale), 2, 2)
                title = f"F{item.get('track_id',0):03d}  {item['name']}  {item['sid']}" if item['sid'] else f"F{item.get('track_id',0):03d}  未知人员 · 待录入"
                p.setFont(QFont('Microsoft YaHei UI', 10))
                tw = p.fontMetrics().horizontalAdvance(title)+22
                tx = max(4, min(r.left(), w-tw-4))
                ty = max(10, r.top()-34)
                p.setPen(QPen(color, 1))
                p.setBrush(QColor(5, 24, 24, 230))
                p.drawRoundedRect(QRectF(tx, ty, tw, 27), 4, 4)
                p.setPen(color)
                p.drawText(QRectF(tx+10, ty, tw-12, 27), Qt.AlignmentFlag.AlignVCenter, title)
        else:
            cx, cy = w/2, h/2-28
            p.setPen(QPen(QColor('#25463d'), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), 94, 94)
            p.drawEllipse(QPointF(cx, cy), 76, 76)
            p.setPen(QPen(QColor('#8df3cf'), 2))
            p.drawArc(QRectF(cx-94,cy-94,188,188), int(self.phase*180/math.pi*16), 50*16)
            self.draw_brackets(p, QRectF(cx-47,cy-47,94,94), QColor('#79bdab'), 21)
            p.setPen(QColor('#8cf5d1'))
            p.setFont(QFont('Microsoft YaHei UI', 16, QFont.Weight.Medium))
            p.drawText(QRectF(0, cy+120, w, 30), Qt.AlignmentFlag.AlignCenter, '视觉引擎 · 待命')
            p.setFont(QFont('Microsoft YaHei UI', 10))
            p.setPen(QColor('#6c9185'))
            p.drawText(QRectF(0, cy+155, w, 25), Qt.AlignmentFlag.AlignCenter, '连接摄像头，或打开图片 / 视频开始检测')
        self.draw_brackets(p, QRectF(10,10,w-20,h-20), QColor('#547d6c'), 20)
        p.fillRect(QRectF(20,20,184,30), QColor(6,23,25,215))
        p.setPen(QColor('#9af3d0'))
        p.setFont(QFont('Consolas', 10))
        p.drawText(QRectF(30,20,165,30), Qt.AlignmentFlag.AlignVCenter, '●  VISION / CHANNEL 01')
        if self.image is not None:
            p.setPen(QColor('#b5d5c9'))
            p.setFont(QFont('Consolas', 9))
            gpu = self.telemetry
            rows = [f"RENDER   {self.render_fps:5.1f} FPS",f"DETECT   {self.stats.get('detect_fps',self.stats.get('fps',0)):5.1f} FPS",f"LATENCY  {self.stats.get('latency',0):5.1f} ms",f"INFER    {self.stats.get('inference_ms',0):5.1f} ms",f"SOURCE   {self.stats.get('source_fps',0):5.1f} FPS",f"FRAME    {self.stats.get('frame_number',0):05d}",f"PEOPLE   {len(self.stats.get('people',[])):02d}   FACE {len(self.stats.get('faces',[])):02d}"]
            if gpu.get('available'):
                util = f"{gpu['util']:5.0f} %" if gpu.get('util') is not None else '  N/A'
                vram = f"{gpu['used']:.0f}/{gpu['total']:.0f} MB" if gpu.get('used') is not None and gpu.get('total') is not None else 'N/A'
                rows += [f"GPU      {util}",f"VRAM     {vram}"]
                if gpu.get('temp') is not None:
                    rows += [f"TEMP     {gpu['temp']:5.0f} C"]
            if gpu.get('cpu_available'):
                cpu = f"{gpu['cpu_util']:5.1f} %" if gpu.get('cpu_util') is not None else '  N/A'
                rows += [f"CPU      {cpu}"]
                if gpu.get('process_ram') is not None:
                    rows += [f"APP RAM  {gpu['process_ram']:5.0f} MB"]
            if 'adaptive_target_fps' in self.stats:
                rows += [f"TARGET   {self.stats['adaptive_target_fps']:5.1f} FPS",f"AGE      {self.stats.get('frame_age_ms',0):5.0f} ms"]
            p.fillRect(QRectF(w-206,20,186,len(rows)*19+18),QColor(5,22,24,215))
            for index,text in enumerate(rows):
                p.drawText(QRectF(w-194,29+index*19,170,19),Qt.AlignmentFlag.AlignVCenter,text)

    @staticmethod
    def draw_brackets(p, r, color, length):
        p.setPen(QPen(color, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for x,y,dx,dy in [(r.left(),r.top(),1,1),(r.right(),r.top(),-1,1),(r.left(),r.bottom(),1,-1),(r.right(),r.bottom(),-1,-1)]:
            p.drawLine(QPointF(x,y), QPointF(x+dx*length,y))
            p.drawLine(QPointF(x,y), QPointF(x,y+dy*length))


class EnrollDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.image = None
        self.setWindowTitle('录入学生 · 家和丨')
        self.setMinimumWidth(430)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(label('建立学生人脸档案', 19, MINT, True))
        layout.addWidget(label('选择清晰单人照，或使用当前摄像头画面', 11, MUTED))
        self.preview = QLabel('尚未选择照片')
        self.preview.setFixedHeight(190)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet('background:#081215; border:1px dashed #345b4e; border-radius:8px;')
        layout.addWidget(self.preview)
        row = QHBoxLayout()
        row.addWidget(button('选择照片', self.choose))
        row.addWidget(button('使用当前画面', self.capture))
        layout.addLayout(row)
        form = QFormLayout()
        self.name = QLineEdit()
        self.sid = QLineEdit()
        self.class_name = QLineEdit()
        self.name.setPlaceholderText('中文姓名')
        self.sid.setPlaceholderText('学号保持原始文本，保留前导零')
        form.addRow('姓名', self.name)
        form.addRow('学号', self.sid)
        form.addRow('班级（可选）', self.class_name)
        layout.addLayout(form)
        layout.addWidget(label('照片和人脸特征仅保存在本机。请使用已获授权的照片。', 10, MUTED))
        layout.addWidget(button('保存人脸档案', self.save, True))

    def show_image(self, image):
        self.image = image.copy()
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        q = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888)
        self.preview.setPixmap(QPixmap.fromImage(q).scaled(390,190,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))

    def choose(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择人脸照片', '', '图片 (*.jpg *.jpeg *.png *.bmp *.webp)')
        if path:
            image = cv2.imdecode(np.fromfile(path,np.uint8),cv2.IMREAD_COLOR)
            if image is not None:
                self.show_image(image)

    def capture(self):
        image = self.window.worker.last_frame
        if image is None:
            QMessageBox.information(self,'暂无画面','请先启动摄像头或打开图片。')
        else:
            self.show_image(image)

    def save(self):
        name, sid = self.name.text().strip(), self.sid.text().strip()
        if not name or not sid or self.image is None:
            QMessageBox.warning(self,'信息不完整','请填写姓名、学号，并选择照片。')
            return
        engine = self.window.worker.engine
        if engine is None:
            QMessageBox.warning(self,'引擎尚未就绪','请等待模型加载完成。')
            return
        try:
            image = self.image
            if image.shape[1] > 1600:
                image = cv2.resize(image,(1600,round(image.shape[0]*1600/image.shape[1])))
            faces = engine.faces(image)
            if len(faces) != 1:
                raise ValueError(f'检测到 {len(faces)} 张人脸，请提供仅包含一张清晰人脸的照片。')
            emb = engine.embedding(image, faces[0])
            path = DATA / 'faces' / f'enroll_{time.time_ns()}.jpg'
            cv2.imencode('.jpg', image)[1].tofile(str(path))
            try:
                self.window.store.enroll(sid,name,self.class_name.text().strip(),emb,str(path))
            except Exception:
                path.unlink(missing_ok=True)
                raise
            engine.reload(self.window.store.students())
            self.window.refresh_students()
            self.accept()
        except sqlite3.IntegrityError:
            QMessageBox.warning(self,'学号已存在','该学号已有档案，请勿重复录入。')
        except Exception as exc:
            QMessageBox.warning(self,'无法录入',str(exc))


class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle('家和丨 · 智能视觉识别')
        self.setWindowIcon(QIcon(str(ROOT / 'assets/logo.png')))
        self.setMinimumSize(960, 620)
        self.resize(1440, 900)
        self.store = Store()
        self.worker = Worker(self.store)
        self.last_stats = {}
        self.last_detection_image = None
        self._drag_start = None
        self._resize_edges = Qt.Edge(0)
        self._resize_origin = None
        self._resize_geometry = None
        self.selected_source = 0
        self.selected_camera_index = None
        self.camera_scanner = None
        self.setMouseTracking(True)
        QApplication.instance().installEventFilter(self)
        self.host_layout = QVBoxLayout(self)
        self.host_layout.setContentsMargins(12,12,12,12)
        self.surface = QFrame()
        self.surface.setObjectName('shell')
        self.host_layout.addWidget(self.surface)
        # Paint the window shadow directly: avoid blurring the full video surface
        # into an offscreen texture on every frame.
        outer = QVBoxLayout(self.surface)
        outer.setContentsMargins(1,1,1,1)
        outer.setSpacing(0)
        self.topbar = Topbar(self)
        outer.addWidget(self.topbar)
        content = QHBoxLayout()
        content.setContentsMargins(10,10,10,6)
        content.setSpacing(10)
        self.sidebar = self.make_sidebar()
        content.addWidget(self.sidebar)
        self.pages = QStackedWidget()
        self.canvas = VideoCanvas()
        self.pages.addWidget(self.canvas)
        self.pages.addWidget(self.make_students_page())
        self.pages.addWidget(self.make_records_page())
        content.addWidget(self.pages,1)
        outer.addLayout(content,1)
        footer = QHBoxLayout()
        footer.setContentsMargins(13,0,13,6)
        self.status = label('正在加载视觉引擎…', 10, MUTED)
        footer.addWidget(self.status,1)
        footer.addWidget(label('LOCAL PROCESSING  /  本地处理',9,'#54786a'))
        outer.addLayout(footer)
        self.make_dock()
        self.scan_cameras()
        self.fullscreen_shortcut = QShortcut(QKeySequence('F11'),self)
        self.fullscreen_shortcut.activated.connect(self.toggle_fullscreen)
        self.escape_shortcut = QShortcut(QKeySequence('Esc'),self)
        self.escape_shortcut.activated.connect(self.exit_fullscreen)
        self.worker.frame_ready.connect(self.on_frame)
        if hasattr(self.worker,'preview_ready'):
            self.worker.preview_ready.connect(self.on_preview)
        self.worker.state.connect(self.status.setText)
        self.worker.failed.connect(self.on_error)
        self.worker.engine_ready.connect(self.engine_ready)
        self.worker.start()
        self.telemetry_worker = None
        try:
            from telemetry import Telemetry
            self.telemetry_worker = Telemetry()
            self.telemetry_worker.updated.connect(self.on_telemetry)
            self.telemetry_worker.start()
        except ImportError:
            pass
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.tick()
        self.refresh_students()
        self.refresh_records()

    def make_sidebar(self):
        panel = QFrame()
        panel.setObjectName('sidebar')
        panel.setFixedWidth(286)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12,12,12,10)
        layout.setSpacing(8)
        title = QHBoxLayout()
        title.addWidget(label('感知总览',17,'#dcf3e7',True))
        title.addStretch()
        title.addWidget(label('● LIVE',10,MINT))
        layout.addLayout(title)
        grid = QGridLayout()
        grid.setSpacing(7)
        self.metrics = {}
        for i,(key,title) in enumerate([('people','当前人体'),('faces','当前人脸'),('known','已识别'),('unique','本次去重学生')]):
            card = QFrame()
            card.setObjectName('card')
            box = QVBoxLayout(card)
            box.setContentsMargins(12,9,8,9)
            box.setSpacing(0)
            value = label('00',30,MINT,True)
            self.metrics[key] = value
            box.addWidget(value)
            box.addWidget(label(title,10,MUTED))
            grid.addWidget(card,i//2,i%2)
        layout.addLayout(grid)
        layout.addWidget(label('当前识别  /  IDENTITIES',11,'#a7c4b6',True))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.results = QWidget()
        self.results.setStyleSheet('background:transparent;')
        self.result_layout = QVBoxLayout(self.results)
        self.result_layout.setContentsMargins(0,0,0,0)
        self.result_layout.setSpacing(7)
        self.result_layout.addWidget(label('等待画面接入\n识别结果将在这里显示',11,MUTED))
        self.result_layout.addStretch()
        scroll.setWidget(self.results)
        layout.addWidget(scroll,1)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet('background:#294238;')
        layout.addWidget(line)
        layout.addWidget(label('引擎状态',11,'#a7c4b6',True))
        self.device = label('○  模型初始化中',11,MUTED)
        self.gallery_label = label('学生库  ·  0 人',11,MUTED)
        self.performance = label('推理延迟  ·  —',11,MUTED)
        self.gpu_metrics = label('GPU 利用率 / 显存  ·  —',10,MUTED)
        layout.addWidget(self.device)
        layout.addWidget(self.gallery_label)
        layout.addWidget(self.performance)
        layout.addWidget(self.gpu_metrics)
        threshold_row = QHBoxLayout()
        threshold_row.addWidget(label('匹配阈值',10,MUTED))
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(.2,.95)
        self.threshold.setSingleStep(.01)
        self.threshold.setValue(.45)
        self.threshold.setFixedWidth(90)
        self.threshold.valueChanged.connect(self.set_threshold)
        threshold_row.addWidget(self.threshold)
        layout.addLayout(threshold_row)
        note = label('相似度并非身份概率；未知人员不计入去重学生。',9,'#54786a')
        note.setWordWrap(True)
        layout.addWidget(note)
        return panel

    def make_dock(self):
        dock = QFrame(self.canvas)
        dock.setObjectName('dock')
        row = QGridLayout(dock)
        row.setContentsMargins(10,9,10,9)
        row.setSpacing(7)
        self.camera = QComboBox()
        self.camera.setObjectName('cameraSelect')
        self.camera.setMinimumWidth(185)
        self.camera.setMaximumWidth(245)
        self.camera.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        self.camera.addItem('正在查找摄像头…',None)
        self.camera.setToolTip('选择编号和名称，立即连接对应摄像头；菜单底部可重新扫描。')
        self.camera.activated.connect(self.camera_selected)
        self.files = button('＋  图片 / 视频',self.open_file)
        self.play = button('▶  开始检测',self.toggle_play,True)
        self.snap = button('▣  截图',self.snapshot)
        self.mesh_toggle = button('面部网格',self.toggle_mesh)
        self.mesh_toggle.setCheckable(True)
        self.mesh_toggle.setChecked(True)
        self.pose_toggle = button('人体骨架',self.toggle_pose)
        self.pose_toggle.setCheckable(True)
        self.pose_toggle.setChecked(True)
        self.checkin_button = button('◎  打卡',self.check_in,True)
        self.fullscreen_button = button('⛶  全屏',self.toggle_fullscreen)
        self.camera_mirror = button('⇋  镜像',self.toggle_mirror)
        self.camera_mirror.setCheckable(True)
        self.camera_mirror.setChecked(True)
        self.camera_mirror.setToolTip('摄像头镜像：默认开启，点击关闭。图片和视频文件保持原方向。')
        self.dock_buttons = [self.camera,self.files,self.play,self.checkin_button,self.camera_mirror,self.mesh_toggle,self.pose_toggle,self.snap,self.fullscreen_button]
        self.dock_layout = row
        self.dock_compact = None
        self.canvas.reflow_dock = self.reflow_dock
        self.reflow_dock(self.canvas.width())
        self.play.setEnabled(False)
        self.camera.setEnabled(False)
        self.files.setEnabled(False)
        shadow = QGraphicsDropShadowEffect(dock)
        shadow.setBlurRadius(28)
        shadow.setOffset(0,7)
        shadow.setColor(QColor(0,0,0,170))
        dock.setGraphicsEffect(shadow)
        self.canvas.dock = dock
        dock.adjustSize()
        dock.show()

    def reflow_dock(self,width):
        compact = width<1000
        if compact==self.dock_compact:
            return
        self.dock_compact = compact
        while self.dock_layout.count():
            self.dock_layout.takeAt(0)
        for index,b in enumerate(self.dock_buttons):
            if compact:
                positions = [(0,0,1,2),(0,2,1,1),(0,3,1,1),(0,4,1,1),(1,0,1,1),(1,1,1,1),(1,2,1,1),(1,3,1,1),(1,4,1,1)]
                self.dock_layout.addWidget(b,*positions[index])
            else:
                self.dock_layout.addWidget(b,0,index)

    def scan_cameras(self):
        if self.camera_scanner is not None and self.camera_scanner.isRunning():
            return
        try:
            from camera_devices import CameraScanner
            self.camera_scanner = CameraScanner(self)
            self.camera_scanner.devices_ready.connect(self.cameras_found)
            self.camera_scanner.failed.connect(self.cameras_failed)
            self.camera_scanner.start()
        except Exception as exc:
            self.cameras_failed(str(exc))

    def cameras_found(self,devices):
        previous = self.selected_camera_index
        self.camera.blockSignals(True)
        self.camera.clear()
        self.worker.camera_names = {d['index']:d['name'] for d in devices}
        icon = QIcon(str(ROOT / 'assets/icons/camera-blue.svg'))
        if devices:
            for item in devices:
                text = f"{item['index']+1:02d} · {item['name']}"
                self.camera.addItem(icon,text,item['index'])
                self.camera.setItemData(self.camera.count()-1,text,Qt.ItemDataRole.ToolTipRole)
            selected = self.camera.findData(previous) if previous is not None else 0
            self.camera.setCurrentIndex(max(0,selected))
            self.selected_camera_index = self.camera.currentData()
        else:
            self.camera.addItem('未发现摄像头',None)
            self.selected_camera_index = None
        self.camera.insertSeparator(self.camera.count())
        self.camera.addItem(QIcon(str(ROOT / 'assets/icons/history-blue.svg')),'重新扫描摄像头','refresh')
        self.camera.blockSignals(False)
        self.camera.setEnabled(self.worker.engine is not None)
        self.camera.setToolTip('已发现 '+str(len(devices))+' 个摄像头。选择设备即可切换；镜像开关对摄像头生效。')
        if self.canvas.dock:
            self.canvas.dock.adjustSize()
            self.canvas.dock.move((self.canvas.width()-self.canvas.dock.width())//2,self.canvas.height()-self.canvas.dock.height()-18)

    def cameras_failed(self,message):
        self.camera.blockSignals(True)
        self.camera.clear()
        self.camera.addItem('摄像头扫描失败',None)
        self.camera.addItem('重新扫描摄像头','refresh')
        self.camera.blockSignals(False)
        self.camera.setToolTip(message)
        self.status.setText('摄像头枚举失败：'+message)

    def camera_selected(self,index):
        selected = self.camera.itemData(index)
        if selected=='refresh':
            restored = self.camera.findData(self.selected_camera_index)
            self.camera.setCurrentIndex(max(0,restored))
            self.scan_cameras()
        elif isinstance(selected,int):
            self.selected_camera_index = selected
            self.open_camera()

    def make_students_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12,10,8,8)
        row = QHBoxLayout()
        row.addWidget(label('学生档案',22,'#d9f5e8',True))
        row.addStretch()
        row.addWidget(button('＋  录入学生',self.enroll,True))
        layout.addLayout(row)
        layout.addWidget(label('本地人脸特征库 · 唯一学号 · 中文姓名',11,MUTED))
        self.students_table = self.table(['照片','姓名 / 学号','基础资料','性格 / 备注','操作'])
        layout.addWidget(self.students_table,1)
        return page

    def make_records_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12,10,8,8)
        row = QHBoxLayout()
        row.addWidget(label('识别记录',22,'#d9f5e8',True))
        row.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索姓名 / 学号')
        self.search.setMaximumWidth(250)
        self.search.textChanged.connect(self.refresh_records)
        row.addWidget(self.search)
        row.addWidget(button('导出 CSV',self.export))
        layout.addLayout(row)
        layout.addWidget(label('仅点击「打卡」时保存截图与当时的人员信息。双击记录查看完整打卡截图。',11,MUTED))
        self.records_table = self.table(['打卡时间','人员','学号','人数','视频源'])
        self.records_table.cellDoubleClicked.connect(self.preview_record)
        layout.addWidget(self.records_table,1)
        return page

    @staticmethod
    def table(headers):
        table = QTableWidget(0,len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().hide()
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setShowGrid(False)
        return table

    def tick(self):
        self.topbar.clock.setText(datetime.now().strftime('%H:%M:%S'))

    def on_telemetry(self,data):
        self.canvas.telemetry = data
        if data.get('available'):
            self.gpu_metrics.setText(f"GPU {data.get('util') or 0:.0f}%  ·  显存 {data.get('used') or 0:.0f}/{data.get('total') or 0:.0f} MB")
        else:
            self.gpu_metrics.setText('GPU 遥测暂不可用')
        if data.get('cpu_available'):
            cpu = f"{data['cpu_util']:.0f}%" if data.get('cpu_util') is not None else '采样中'
            memory = f"{data.get('process_ram',0):.0f} MB" if data.get('process_ram') is not None else '—'
            self.gpu_metrics.setText(f'CPU {cpu}  ·  程序内存 {memory}')
        self.canvas.update()

    def toggle_mirror(self):
        self.worker.mirror_camera = self.camera_mirror.isChecked()
        self.camera_mirror.setToolTip('摄像头镜像：'+('开启' if self.camera_mirror.isChecked() else '关闭')+'。图片和视频文件保持原方向。')
        self.status.setText('摄像头镜像已'+('开启' if self.camera_mirror.isChecked() else '关闭'))

    def toggle_mesh(self):
        self.canvas.mesh_enabled = self.mesh_toggle.isChecked()
        self.worker.landmarks_enabled = self.canvas.mesh_enabled or self.canvas.pose_enabled
        self.canvas.update()

    def toggle_pose(self):
        self.canvas.pose_enabled = self.pose_toggle.isChecked()
        self.worker.landmarks_enabled = self.canvas.mesh_enabled or self.canvas.pose_enabled
        self.canvas.update()

    def engine_ready(self,engine):
        self.device.setText('●  CPU 视觉引擎在线')
        self.device.setStyleSheet(f'color:{MINT};')
        self.play.setEnabled(True)
        self.camera.setEnabled(True)
        self.files.setEnabled(True)
        if engine.warning:
            self.status.setText(engine.warning)

    def set_threshold(self,value):
        if self.worker.engine:
            self.worker.engine.threshold = value

    def change_tab(self,index):
        self.pages.setCurrentIndex(index)
        for i,b in enumerate(self.topbar.tabs):
            b.setChecked(i==index)
        if index==1:
            self.refresh_students()
        if index==2:
            self.refresh_records()

    def open_camera(self):
        index = self.selected_camera_index
        if index is None:
            QMessageBox.information(self,'未选择摄像头','请选择可用摄像头，或在下拉菜单中重新扫描。')
            return
        self.change_tab(0)
        self.selected_source = index
        self.canvas.stats = {}
        self.last_stats = {}
        self.worker.open_source(index)
        self.play.setText('Ⅱ  暂停检测')
        self.status.setText('正在连接摄像头…')

    def open_file(self):
        path,_ = QFileDialog.getOpenFileName(self,'打开图片或视频','','媒体 (*.jpg *.jpeg *.png *.bmp *.webp *.mp4 *.avi *.mkv *.mov)')
        if path:
            self.change_tab(0)
            self.selected_source = path
            self.canvas.stats = {}
            self.last_stats = {}
            self.worker.open_source(path)
            self.play.setText('Ⅱ  暂停检测')
            self.status.setText('正在分析：'+Path(path).name)

    def toggle_play(self):
        if self.worker.active:
            self.worker.active = False
            self.play.setText('▶  继续检测')
            self.status.setText('检测已暂停')
        elif self.worker.source is None:
            self.open_camera()
        else:
            if self.worker.ended:
                self.worker.open_source(self.worker.source)
            else:
                self.worker.active = True
            self.play.setText('Ⅱ  暂停检测')

    def on_preview(self,image):
        self.canvas.image = image
        self.canvas.update()

    def on_frame(self,image,stats):
        self.last_stats = stats
        self.last_detection_image = image
        self.canvas.set_frame(image if self.worker.image_mode or self.canvas.image is None else self.canvas.image,stats)
        counts = {'people':len(stats['people']),'faces':len(stats['faces']),'known':sum(bool(f['sid']) for f in stats['faces']),'unique':stats['unique']}
        for key,value in counts.items():
            self.metrics[key].setText(f'{value:02d}')
        self.performance.setText(f"检测 {stats.get('detect_fps',stats['fps']):.1f} FPS  ·  延迟 {stats['latency']:.0f} ms")
        while self.result_layout.count():
            item = self.result_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for face in stats['faces']:
            card = QFrame()
            card.setObjectName('card')
            row = QHBoxLayout(card)
            row.setContentsMargins(8,8,8,8)
            x,y,w,h = face['box']
            crop = image[max(0,y):max(0,y)+h,max(0,x):max(0,x)+w]
            photo = QLabel()
            photo.setFixedSize(46,55)
            if crop.size:
                rgb = cv2.cvtColor(crop,cv2.COLOR_BGR2RGB)
                q = QImage(rgb.data,rgb.shape[1],rgb.shape[0],rgb.strides[0],QImage.Format.Format_RGB888)
                photo.setPixmap(QPixmap.fromImage(q).scaled(46,55,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
            row.addWidget(photo)
            info = QVBoxLayout()
            info.setSpacing(2)
            info.addWidget(label(face['name'],14,MINT if face['sid'] else '#ffc885',True))
            info.addWidget(label(face['sid'] or '未匹配到学生档案',10,MUTED))
            info.addWidget(label(f"会话追踪 F{face.get('track_id',0):03d}",9,'#78a292'))
            info.addWidget(label(f"相似度  {face['score']:.3f}" if face['sid'] else '等待录入 / 调整拍摄角度',9,'#6c9b87'))
            profile = self.store.profile(face['sid']) if face['sid'] else None
            if profile:
                values = []
                if profile['age'] is not None: values.append(f"{profile['age']}岁")
                if profile['gender']: values.append(profile['gender'])
                if profile['height_cm'] is not None: values.append(f"{profile['height_cm']:g}cm")
                if profile['weight_jin'] is not None: values.append(f"{profile['weight_jin']:g}斤")
                details = label(' · '.join(values),9,'#92b6a4')
                details.setWordWrap(True)
                info.addWidget(details)
                extra = ' / '.join(v for v in [profile['personality'],profile['appearance_note']] if v)
                if extra:
                    details = label(extra,9,'#6b9783')
                    details.setWordWrap(True)
                    info.addWidget(details)
            row.addLayout(info,1)
            self.result_layout.addWidget(card)
        if not stats['faces']:
            self.result_layout.addWidget(label('当前画面未发现清晰人脸',11,MUTED))
        self.result_layout.addStretch()
        quality = stats.get('quality_label','CPU 本地分析')
        self.status.setText(f"{stats['source']}  ·  CPU  ·  {image.shape[1]} × {image.shape[0]}  ·  {quality}")
        if self.worker.image_mode:
            self.play.setText('▶  重新检测')

    def on_error(self,message):
        self.status.setText(message)
        self.play.setText('▶  开始检测')
        QMessageBox.warning(self,'检测提示',message)

    def enroll(self):
        if self.worker.engine is None:
            QMessageBox.information(self,'正在准备','模型尚未就绪，请稍候。')
            return
        EnrollDialog(self).exec()

    def refresh_students(self):
        students = self.store.students()
        profiles = self.store.profiles()
        self.gallery_label.setText(f'学生库  ·  {len(students)} 人')
        self.students_table.setRowCount(len(students))
        for i,row in enumerate(students):
            sid,name,cls,emb,photo = row
            pic = QLabel()
            pic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pic.setPixmap(QPixmap(photo).scaled(48,55,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
            self.students_table.setCellWidget(i,0,pic)
            profile = profiles.get(sid,{})
            basic = ' · '.join(v for v in [str(profile.get('age') or '')+('岁' if profile.get('age') is not None else ''),profile.get('gender') or '',str(profile.get('height_cm') or '')+('cm' if profile.get('height_cm') is not None else ''),str(profile.get('weight_jin') or '')+('斤' if profile.get('weight_jin') is not None else '')] if v)
            for col,text in enumerate([name+'\n'+sid,basic or '资料待完善',' / '.join(v for v in [profile.get('personality'),profile.get('appearance_note')] if v) or '—'],1):
                self.students_table.setItem(i,col,QTableWidgetItem(text))
            self.students_table.setRowHeight(i,78)
            actions = QWidget()
            actions_row = QHBoxLayout(actions)
            actions_row.setContentsMargins(3,4,3,4)
            actions_row.setSpacing(4)
            actions_row.addWidget(button('编辑',lambda checked=False,s=sid:self.edit_profile(s)))
            actions_row.addWidget(button('删除',lambda checked=False,s=sid:self.delete_student(s)))
            self.students_table.setCellWidget(i,4,actions)

    def edit_profile(self,sid):
        profile = self.store.profile(sid)
        if not profile:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('编辑档案 · '+profile['name'])
        dialog.setMinimumWidth(420)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label(profile['name']+'  '+sid,18,MINT,True))
        form = QFormLayout()
        entries = {}
        for key,title in [('age','年龄'),('gender','性别'),('height_cm','身高（cm）'),('weight_jin','体重（斤）'),('personality','性格'),('appearance_note','备注')]:
            entry = QLineEdit('' if profile[key] is None else str(profile[key]))
            form.addRow(title,entry)
            entries[key] = entry
        layout.addLayout(form)
        layout.addWidget(label('以上为人工录入资料，不由摄像头推断。',10,MUTED))
        def save():
            try:
                values = {key:entry.text().strip() for key,entry in entries.items()}
                for key in ['age','height_cm','weight_jin']:
                    values[key] = (int(values[key]) if key=='age' else float(values[key])) if values[key] else None
                    if values[key] is not None and values[key]<0:
                        raise ValueError('年龄、身高、体重应为非负数')
                self.store.update_profile(sid,**values)
                self.refresh_students()
                dialog.accept()
            except ValueError as exc:
                QMessageBox.warning(dialog,'请检查资料','数值字段格式不正确：'+str(exc))
        layout.addWidget(button('保存资料',save,True))
        dialog.exec()

    def delete_student(self,sid):
        if QMessageBox.question(self,'删除档案','确认删除该学生档案及对应人脸特征？历史识别记录将保留。') != QMessageBox.StandardButton.Yes:
            return
        with self.store.lock:
            photo = self.store.db.execute('SELECT photo FROM students WHERE student_id=?',(sid,)).fetchone()
            self.store.db.execute('DELETE FROM students WHERE student_id=?',(sid,))
            self.store.db.commit()
        if photo and photo[0]:
            path = Path(photo[0]).resolve()
            if path.is_relative_to((DATA / 'faces').resolve()):
                path.unlink(missing_ok=True)
        if self.worker.engine:
            self.worker.engine.reload(self.store.students())
        self.refresh_students()

    def refresh_records(self):
        self.record_rows = self.store.checkins(self.search.text())
        self.records_table.setRowCount(len(self.record_rows))
        for i,row in enumerate(self.record_rows):
            people = row['people']
            values = [row['created_at'].replace('T',' '),'、'.join(p['name'] for p in people) or '未识别到人脸',' / '.join(p.get('sid','') for p in people) or '—',str(len(people)),row['source']]
            for col,text in enumerate(values):
                self.records_table.setItem(i,col,QTableWidgetItem(text))
            self.records_table.setRowHeight(i,42)

    def preview_record(self,row,col):
        record = self.record_rows[row]
        path = record['screenshot']
        if not path or not Path(path).exists():
            QMessageBox.information(self,'暂无抓拍','该条记录没有可用抓拍。')
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('打卡记录 · '+record['created_at'])
        layout = QVBoxLayout(dialog)
        pic = QLabel()
        pic.setPixmap(QPixmap(path).scaled(900,650,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(pic)
        layout.addWidget(label(record['created_at']+'  '+record['source'],12,MINT))
        for person in record['people']:
            profile = person.get('profile') or {}
            detail = ' · '.join(str(v) for v in [person['name'],person.get('sid'),profile.get('age'),profile.get('gender'),profile.get('height_cm'),profile.get('weight_jin'),profile.get('personality'),profile.get('appearance_note')] if v is not None and v!='')
            layout.addWidget(label(detail,11,'#a8c9b9'))
        dialog.exec()

    def export(self):
        path,_ = QFileDialog.getSaveFileName(self,'导出识别记录','家和识别记录.csv','CSV (*.csv)')
        if path:
            self.store.export_checkins(path)
            self.status.setText('已导出记录：'+path)

    def snapshot(self):
        if self.canvas.image is None:
            QMessageBox.information(self,'暂无画面','请先启动检测。')
            return
        path,_ = QFileDialog.getSaveFileName(self,'保存检测截图',datetime.now().strftime('家和_%Y%m%d_%H%M%S.png'),'PNG (*.png)')
        if not path:
            return
        self.detection_image().save(path)
        self.status.setText('中文检测截图已保存：'+path)

    def detection_image(self):
        source = self.last_detection_image if self.last_detection_image is not None else self.canvas.image
        image = Image.fromarray(cv2.cvtColor(source,cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',20)
        for x,y,w,h in self.last_stats.get('people',[]):
            draw.rectangle((x,y,x+w,y+h),outline='#719fa8',width=2)
        if self.canvas.mesh_enabled:
            for mesh in self.last_stats.get('mesh',[]):
                for a,b in self.last_stats.get('mesh_edges',[]):
                    if a<len(mesh) and b<len(mesh):
                        draw.line((mesh[a][0],mesh[a][1],mesh[b][0],mesh[b][1]),fill='#4a9f89',width=1)
        if self.canvas.pose_enabled:
            for pose in self.last_stats.get('poses',[]):
                for a,b in self.last_stats.get('pose_edges',[]):
                    if a<len(pose) and b<len(pose) and pose[a][2]>.5 and pose[b][2]>.5:
                        draw.line((pose[a][0],pose[a][1],pose[b][0],pose[b][1]),fill='#7ddcf5',width=2)
        for face in self.last_stats.get('faces',[]):
            x,y,w,h = face['box']
            color = '#8cf5d1' if face['sid'] else '#ffc885'
            draw.rectangle((x,y,x+w,y+h),outline=color,width=3)
            title = f"F{face.get('track_id',0):03d}  "+face['name']+' '+face['sid']
            ty = max(0,y-32)
            bounds = draw.textbbox((x,ty),title,font=font)
            draw.rectangle((bounds[0]-3,bounds[1]-3,bounds[2]+5,bounds[3]+3),fill='#0a2220')
            draw.text((x,ty),title,font=font,fill=color)
        title = datetime.now().strftime('家和丨  %Y-%m-%d %H:%M:%S')
        draw.rectangle((0,image.height-34,image.width,image.height),fill='#0a2220')
        draw.text((8,image.height-31),title,font=font,fill='#b5ffe1')
        return image

    def check_in(self):
        if self.canvas.image is None:
            QMessageBox.information(self,'暂无画面','请先启动检测，再点击打卡。')
            return
        folder = DATA / 'checkins'
        folder.mkdir(exist_ok=True)
        path = folder / (datetime.now().strftime('%Y%m%d_%H%M%S_')+str(time.time_ns())[-6:]+'.png')
        people = [{'sid':face['sid'],'name':face['name'],'score':float(face['score']),'track_id':face.get('track_id'), 'profile':self.store.profile(face['sid']) if face['sid'] else None} for face in self.last_stats.get('faces',[])]
        try:
            self.detection_image().save(path)
            record_id = self.store.checkin(self.last_stats.get('source',''),str(path),people)
        except Exception as exc:
            path.unlink(missing_ok=True)
            QMessageBox.warning(self,'打卡失败',str(exc))
            return
        self.refresh_records()
        self.status.setText(f'打卡成功 #{record_id} · 已保存截图及 {len(people)} 人信息')
        self.checkin_button.setText('✓  已打卡')
        self.checkin_button.setEnabled(False)
        QTimer.singleShot(900,lambda:(self.checkin_button.setText('◎  打卡'),self.checkin_button.setEnabled(True)))

    def toggle_max(self):
        if self.isFullScreen():
            self.exit_fullscreen()
        else:
            self.showNormal() if self.isMaximized() else self.showMaximized()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.exit_fullscreen()
        else:
            self._was_maximized = self.isMaximized()
            self.showFullScreen()
            self.fullscreen_button.setText('⛶  退出全屏')

    def exit_fullscreen(self):
        if self.isFullScreen():
            self.showMaximized() if getattr(self,'_was_maximized',False) else self.showNormal()
            self.fullscreen_button.setText('⛶  全屏')

    def resizeEvent(self,event):
        if hasattr(self,'sidebar'):
            self.sidebar.setFixedWidth(max(230,min(286,round(self.width()*.215))))
        super().resizeEvent(event)

    def changeEvent(self,event):
        if event.type()==QEvent.Type.WindowStateChange and hasattr(self,'host_layout'):
            maximized = self.isMaximized() or self.isFullScreen()
            self.host_layout.setContentsMargins(0,0,0,0) if maximized else self.host_layout.setContentsMargins(12,12,12,12)
            self.surface.setStyleSheet('QFrame#shell {border-radius:0px;}' if maximized else '')
        super().changeEvent(event)

    def paintEvent(self,event):
        if not self.isMaximized() and not self.isFullScreen():
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            for spread in range(12,0,-1):
                p.setBrush(QColor(0,0,0,3+int((12-spread)*.7)))
                p.drawRoundedRect(QRectF(12-spread,14-spread,self.width()-24+spread*2,self.height()-26+spread*2),14+spread,14+spread)
        super().paintEvent(event)

    def eventFilter(self,obj,event):
        kinds = (QEvent.Type.MouseMove,QEvent.Type.MouseButtonPress,QEvent.Type.MouseButtonRelease,QEvent.Type.MouseButtonDblClick)
        if event.type() in kinds and self.isVisible() and isinstance(obj,QWidget) and QWidget.window(obj) is self:
            global_point = event.globalPosition().toPoint()
            point = self.mapFromGlobal(global_point)
            edges = self.resize_edges_at(point.x(),point.y())
            if event.type()==QEvent.Type.MouseButtonRelease and event.button()==Qt.MouseButton.LeftButton:
                if self._drag_start is not None or self._resize_edges:
                    self._drag_start = None
                    self._resize_edges = Qt.Edge(0)
                    self.releaseMouse()
                    return True
            if event.type()==QEvent.Type.MouseMove:
                if self._resize_edges and event.buttons() & Qt.MouseButton.LeftButton:
                    self.resize_from_pointer(global_point)
                    return True
                if self._drag_start is not None and event.buttons() & Qt.MouseButton.LeftButton:
                    self.move(global_point-self._drag_start)
                    return True
                if edges:
                    horizontal = edges & (Qt.Edge.LeftEdge|Qt.Edge.RightEdge)
                    vertical = edges & (Qt.Edge.TopEdge|Qt.Edge.BottomEdge)
                    diagonal = bool(edges & Qt.Edge.LeftEdge)==bool(edges & Qt.Edge.TopEdge)
                    self.setCursor((Qt.CursorShape.SizeFDiagCursor if diagonal else Qt.CursorShape.SizeBDiagCursor) if horizontal and vertical else Qt.CursorShape.SizeHorCursor if horizontal else Qt.CursorShape.SizeVerCursor)
                else:
                    self.unsetCursor()
            if event.type()==QEvent.Type.MouseButtonPress and event.button()==Qt.MouseButton.LeftButton:
                if edges:
                    self._resize_edges = edges
                    self._resize_origin = global_point
                    self._resize_geometry = QRect(self.geometry())
                    self.grabMouse()
                    return True
                if self.is_title_target(obj):
                    if self.isFullScreen():
                        return False
                    if self.isMaximized():
                        ratio = point.x()/max(self.width(),1)
                        self.showNormal()
                        self.move(global_point.x()-int(self.width()*ratio),global_point.y()-25)
                    self._drag_start = global_point-self.frameGeometry().topLeft()
                    self.grabMouse()
                    return True
            if event.type()==QEvent.Type.MouseButtonDblClick and event.button()==Qt.MouseButton.LeftButton and self.is_title_target(obj):
                self.toggle_max()
                return True
        return super().eventFilter(obj,event)

    def is_title_target(self,obj):
        if isinstance(obj,(QPushButton,QLineEdit,QDoubleSpinBox,QSpinBox,QComboBox)):
            return False
        parent = obj
        while parent is not None:
            if parent is self.topbar:
                return True
            parent = parent.parentWidget()
        return False

    def resize_edges_at(self,x,y):
        edges = Qt.Edge(0)
        if self.isMaximized() or self.isFullScreen():
            return edges
        if x<20: edges |= Qt.Edge.LeftEdge
        if x>self.width()-20: edges |= Qt.Edge.RightEdge
        if y<20: edges |= Qt.Edge.TopEdge
        if y>self.height()-20: edges |= Qt.Edge.BottomEdge
        return edges

    def resize_from_pointer(self,point):
        rect = QRect(self._resize_geometry)
        delta = point-self._resize_origin
        edges = self._resize_edges
        if edges & Qt.Edge.LeftEdge: rect.setLeft(min(rect.right()-self.minimumWidth()+1,rect.left()+delta.x()))
        if edges & Qt.Edge.RightEdge: rect.setRight(max(rect.left()+self.minimumWidth()-1,rect.right()+delta.x()))
        if edges & Qt.Edge.TopEdge: rect.setTop(min(rect.bottom()-self.minimumHeight()+1,rect.top()+delta.y()))
        if edges & Qt.Edge.BottomEdge: rect.setBottom(max(rect.top()+self.minimumHeight()-1,rect.bottom()+delta.y()))
        self.setGeometry(rect)

    def closeEvent(self,event):
        if self.camera_scanner is not None and self.camera_scanner.isRunning():
            self.camera_scanner.wait(1500)
        if self.telemetry_worker:
            self.telemetry_worker.requestInterruption()
            self.telemetry_worker.wait(2500)
        self.worker.stopping = True
        self.worker.active = False
        if not self.worker.wait(3000):
            self.status.setText('正在释放视频源，请稍候…')
            event.ignore()
            QTimer.singleShot(500,self.close)
            return
        QApplication.instance().removeEventFilter(self)
        event.accept()


if __name__=='__main__':
    if sys.platform=='win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('JiaHe.Vision.Desktop.1')
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    app.setFont(QFont('Microsoft YaHei UI',10))
    app.setWindowIcon(QIcon(str(ROOT / 'assets/logo.png')))
    window = Window()
    screen = app.primaryScreen()
    if screen:
        available = screen.availableGeometry()
        window.resize(min(1440,available.width()-24),min(900,available.height()-24))
        window.move(available.center()-window.rect().center())
    window.show()
    if '--source' in sys.argv:
        source_index = sys.argv.index('--source')+1
        if source_index<len(sys.argv):
            source = sys.argv[source_index]
            window.worker.engine_ready.connect(lambda engine:window.worker.open_source(source))
    sys.exit(app.exec())
