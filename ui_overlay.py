import sys
import os
from collections import deque
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QHBoxLayout, 
                             QFrame, QApplication, QSizeGrip, QTextEdit)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QFont, QColor, QPalette, QTextCursor
from core_workers import AudioRecorderThread, WhisperWorkerThread
from core_utils import ConfigManager

class ResizableSubtitleWindow(QWidget):
    closed_signal = pyqtSignal()
    MARGIN = 10 

    def __init__(self, config):
        super().__init__()
        self.config = config
        
        # 1. 窗口属性
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        
        # 2. 恢复尺寸
        w = config.get("window_width", 1000)
        h = config.get("window_height", 200)
        self.resize(w, h)
        
        # 居中
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - self.width()) // 2, screen.height() - 300)

        # 3. 初始化 UI
        self.setup_ui()
        self.start_threads()
        
        # 4. 拖拽状态
        self.is_moving = False
        self.is_resizing = False
        self.drag_pos = QPoint()
        self.resize_edge = None

    def setup_ui(self):
        # 背景容器
        self.container = QFrame(self)
        self.container.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 160); 
                border-radius: 15px;
                border: 1px solid rgba(255, 255, 255, 30);
            }
        """)
        
        # 主布局
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.container)
        
        # 内部布局
        inner_layout = QVBoxLayout(self.container)
        inner_layout.setContentsMargins(10, 5, 10, 10)
        
        # --- 顶部栏 (关闭按钮) ---
        top_bar = QHBoxLayout()
        top_bar.addStretch()
        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet("""
            QPushButton{color:rgba(255,255,255,0.7); background:transparent; font-size:18px; font-weight:bold; border:none;} 
            QPushButton:hover{color:#ff4444;}
        """)
        self.close_btn.clicked.connect(self.close_app)
        top_bar.addWidget(self.close_btn)
        inner_layout.addLayout(top_bar)
        
        # --- 核心修改：使用 QTextEdit 代替 QLabel ---
        self.text_area = QTextEdit(self)
        self.text_area.setReadOnly(True) # 只读
        
        # 样式：透明背景，无边框
        self.text_area.setStyleSheet("background: transparent; border: none;")
        
        # 设置字体
        font_size = self.config.get("font_size", 24)
        font = QFont("Microsoft YaHei UI", font_size)
        font.setBold(True)
        self.text_area.setFont(font)
        
        # 关键：让鼠标事件穿透 TextEdit，这样按住文字也能拖动窗口
        self.text_area.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        # 隐藏滚动条 (看起来像纯文本，但其实是可滚动的)
        self.text_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        inner_layout.addWidget(self.text_area)

        # 右下角手柄
        self.size_grip = QSizeGrip(self.container)
        self.size_grip.setStyleSheet("background-color: transparent;") 

    def start_threads(self):
        self.recorder = AudioRecorderThread()
        self.recorder.start()
        
        self.worker = WhisperWorkerThread(self.config)
        self.worker.update_text_signal.connect(self.add_text)
        self.worker.start()

    def add_text(self, text):
        if text.startswith("❌"):
            # 如果出错，用红色显示
            self.text_area.setTextColor(QColor("#FF4444"))
            self.text_area.append(text)
        else:
            # 正常字幕，亮绿色
            self.text_area.setTextColor(QColor("#00FF7F"))
            self.text_area.append(text)
            
            # 自动滚动到底部
            cursor = self.text_area.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.text_area.setTextCursor(cursor)

    # --- 窗口大小改变 ---
    def resizeEvent(self, event):
        self.config["window_width"] = self.width()
        self.config["window_height"] = self.height()
        # 保持手柄在右下角
        self.size_grip.move(self.width() - 20, self.height() - 20)
        super().resizeEvent(event)

    # --- 鼠标交互逻辑 (拖拽窗口) ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self.get_edge(event.pos())
            if edge:
                self.is_resizing = True
                self.resize_edge = edge
                self.drag_pos = event.globalPosition().toPoint()
            else:
                self.is_moving = True
                self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if not event.buttons():
            edge = self.get_edge(event.pos())
            if edge: self.setCursor(self.get_cursor(edge))
            else: self.setCursor(Qt.CursorShape.ArrowCursor)
        
        if self.is_moving and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()

        if self.is_resizing and event.buttons() == Qt.MouseButton.LeftButton:
            global_pos = event.globalPosition().toPoint()
            rect = self.geometry()
            
            # 只允许向右和向下改变大小，防止坐标错乱
            if "right" in self.resize_edge:
                rect.setWidth(global_pos.x() - rect.x())
            if "bottom" in self.resize_edge:
                rect.setHeight(global_pos.y() - rect.y())
            
            # 限制最小尺寸
            if rect.width() < 300: rect.setWidth(300)
            if rect.height() < 100: rect.setHeight(100)
            
            self.setGeometry(rect)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.is_moving = False
        self.is_resizing = False
        self.resize_edge = None
        ConfigManager.save_config(self.config)

    def get_edge(self, pos):
        edge = ""
        r = self.rect()
        if pos.x() >= r.width() - self.MARGIN: edge += "right"
        if pos.y() >= r.height() - self.MARGIN: edge += "bottom"
        return edge if edge else None

    def get_cursor(self, edge):
        if edge == "right": return Qt.CursorShape.SizeHorCursor
        if edge == "bottom": return Qt.CursorShape.SizeVerCursor
        if "right" in edge and "bottom" in edge: return Qt.CursorShape.SizeFDiagCursor
        return Qt.CursorShape.ArrowCursor

    def close_app(self):
        ConfigManager.save_config(self.config)
        print("正在强制关闭...")
        os._exit(0)