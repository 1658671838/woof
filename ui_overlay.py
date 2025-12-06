import sys
import os  # 引入系统库
from collections import deque
from PyQt6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QPushButton, QHBoxLayout, 
                             QFrame, QApplication, QSizeGrip)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QFont, QFontMetrics
from core_workers import AudioRecorderThread, WhisperWorkerThread
from core_utils import ConfigManager

class ResizableSubtitleWindow(QWidget):
    closed_signal = pyqtSignal()
    MARGIN = 10 

    def __init__(self, config):
        super().__init__()
        self.config = config
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        
        w = config.get("window_width", 1000)
        h = config.get("window_height", 200)
        self.resize(w, h)
        
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - self.width()) // 2, screen.height() - 300)

        self.setup_ui()
        self.text_buffer = deque(maxlen=50) 
        self.start_threads()
        
        self.is_moving = False
        self.is_resizing = False
        self.drag_pos = QPoint()
        self.resize_edge = None

    def setup_ui(self):
        self.container = QFrame(self)
        self.container.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 160); 
                border-radius: 15px;
                border: 1px solid rgba(255, 255, 255, 30);
            }
        """)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.container)
        
        inner_layout = QVBoxLayout(self.container)
        inner_layout.setContentsMargins(15, 10, 15, 15)
        
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
        
        self.label = QLabel("Waiting for audio...", self)
        font_size = self.config.get("font_size", 24)
        self.current_font = QFont("Microsoft YaHei UI", font_size)
        self.current_font.setBold(True)
        self.label.setFont(self.current_font)
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        self.label.setWordWrap(True)
        self.label.setStyleSheet("color: #00FF7F; border: none;")
        inner_layout.addWidget(self.label, 1)

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
            self.label.setText(text)
            self.label.setStyleSheet("color: #FF4444;")
        else:
            self.label.setStyleSheet("color: #00FF7F;")
            self.text_buffer.append(text)
            self.refresh_display_content()

    def refresh_display_content(self):
        if not self.text_buffer: return
        fm = QFontMetrics(self.current_font)
        line_height = fm.lineSpacing() + 5
        available_height = self.container.height() - 55 
        max_lines_possible = max(1, available_height // line_height)
        lines_to_show = list(self.text_buffer)[-max_lines_possible:]
        display_text = "\n".join(lines_to_show)
        self.label.setText(display_text)

    def resizeEvent(self, event):
        self.config["window_width"] = self.width()
        self.config["window_height"] = self.height()
        self.size_grip.move(self.width() - 20, self.height() - 20)
        self.refresh_display_content()
        super().resizeEvent(event)

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
            if "right" in self.resize_edge: rect.setWidth(global_pos.x() - rect.x())
            if "bottom" in self.resize_edge: rect.setHeight(global_pos.y() - rect.y())
            if rect.width() < 300: rect.setWidth(300)
            if rect.height() < 80: rect.setHeight(80)
            self.setGeometry(rect)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.is_moving = False; self.is_resizing = False; self.resize_edge = None
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
        # 1. 保存配置
        ConfigManager.save_config(self.config)
        
        # 2. 暴力退出：直接通知操作系统杀掉当前进程
        # 这会跳过所有线程清理步骤，彻底解决 OleInitialize 报错
        print("正在强制关闭...")
        os._exit(0)