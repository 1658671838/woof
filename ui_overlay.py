import sys
from collections import deque
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton, QHBoxLayout, QFrame, QApplication, QSizeGrip
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRect
from PyQt6.QtGui import QFont, QCursor
from core_workers import AudioRecorderThread, WhisperWorkerThread
from core_utils import ConfigManager

class ResizableSubtitleWindow(QWidget):
    closed_signal = pyqtSignal()
    
    # 边缘判定距离 (鼠标靠近边缘 5px 变成缩放图标)
    MARGIN = 10 

    def __init__(self, config):
        super().__init__()
        self.config = config
        
        # 1. 窗口属性：无边框、置顶、半透明
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # 启用鼠标追踪 (为了检测鼠标是否在边缘)
        self.setMouseTracking(True)
        
        # 恢复上次保存的大小
        w = config.get("window_width", 1000)
        h = config.get("window_height", 150)
        self.resize(w, h)
        
        # 居中
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - self.width()) // 2, screen.height() - 250)

        # 2. 界面布局
        self.setup_ui()
        
        # 3. 启动线程
        self.start_threads()
        
        # 状态变量
        self.is_moving = False
        self.is_resizing = False
        self.drag_pos = QPoint()
        self.resize_edge = None # 记录正在拖动哪个边缘

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
        self.layout.setContentsMargins(0, 0, 0, 0) # 贴边
        self.layout.addWidget(self.container)
        
        # 容器内部布局
        inner_layout = QVBoxLayout(self.container)
        
        # 顶部栏 (关闭按钮)
        top_bar = QHBoxLayout()
        top_bar.addStretch()
        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet("QPushButton{color:white; background:transparent; font-size:18px; font-weight:bold;} QPushButton:hover{color:#ff4444;}")
        self.close_btn.clicked.connect(self.close_app)
        top_bar.addWidget(self.close_btn)
        inner_layout.addLayout(top_bar)
        
        # 字幕显示 Label
        self.label = QLabel("初始化...", self)
        font = QFont("Microsoft YaHei UI", self.config.get("font_size", 24))
        font.setBold(True)
        self.label.setFont(font)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True) # 关键：让文字随窗口自动换行
        self.label.setStyleSheet("color: #00FF7F; padding: 5px;")
        
        inner_layout.addWidget(self.label)
        inner_layout.addStretch()
        
        # 右下角添加一个显眼的调整手柄 (可选，辅助用户识别)
        self.size_grip = QSizeGrip(self.container)
        self.size_grip.setStyleSheet("width: 15px; height: 15px; background-color: rgba(255,255,255,50); border-top-left-radius: 15px;")
        # 将手柄放到右下角
        # 注意：QSizeGrip 在布局里自动吸附右下角，但由于我们用了布局嵌套，可能需要resizeEvent里手动定位
    
    def resizeEvent(self, event):
        # 当窗口大小改变时，保存配置
        self.config["window_width"] = self.width()
        self.config["window_height"] = self.height()
        
        # 确保 size_grip 永远在右下角
        self.size_grip.move(self.width() - 20, self.height() - 20)
        super().resizeEvent(event)

    def start_threads(self):
        self.recorder = AudioRecorderThread()
        self.recorder.start()
        
        self.worker = WhisperWorkerThread(self.config)
        self.worker.update_text_signal.connect(self.update_text)
        self.worker.start()
        self.text_buffer = deque(maxlen=2)

    def update_text(self, text):
        if text.startswith("❌"):
            self.label.setText(text)
            self.label.setStyleSheet("color: #FF4444;")
        else:
            self.text_buffer.append(text)
            self.label.setText("\n".join(self.text_buffer))
            self.label.setStyleSheet("color: #00FF7F;")

    # --- 核心：手动实现窗口拖拽和缩放逻辑 ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # 判断鼠标位置
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
        # 1. 如果没有按键，只是移动 -> 改变鼠标形状提示用户
        if not event.buttons():
            edge = self.get_edge(event.pos())
            if edge:
                self.setCursor(self.get_cursor(edge))
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        
        # 2. 如果正在拖拽移动
        if self.is_moving and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()

        # 3. 如果正在缩放 (简化版：只支持右侧和下侧，为了稳定性)
        if self.is_resizing and event.buttons() == Qt.MouseButton.LeftButton:
            global_pos = event.globalPosition().toPoint()
            rect = self.geometry()
            
            if "right" in self.resize_edge:
                rect.setWidth(global_pos.x() - rect.x())
            if "bottom" in self.resize_edge:
                rect.setHeight(global_pos.y() - rect.y())
            
            # 最小尺寸限制
            if rect.width() < 300: rect.setWidth(300)
            if rect.height() < 100: rect.setHeight(100)
            
            self.setGeometry(rect)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.is_moving = False
        self.is_resizing = False
        self.resize_edge = None
        # 保存尺寸到配置
        ConfigManager.save_config(self.config)

    def get_edge(self, pos):
        # 判断鼠标是否在边缘区域
        edge = ""
        r = self.rect()
        # 这里只做右边和下边的缩放，比较简单且符合习惯
        if pos.x() >= r.width() - self.MARGIN:
            edge += "right"
        if pos.y() >= r.height() - self.MARGIN:
            edge += "bottom"
        return edge if edge else None

    def get_cursor(self, edge):
        if edge == "right": return Qt.CursorShape.SizeHorCursor
        if edge == "bottom": return Qt.CursorShape.SizeVerCursor
        if "right" in edge and "bottom" in edge: return Qt.CursorShape.SizeFDiagCursor
        return Qt.CursorShape.ArrowCursor

    def close_app(self):
        if self.recorder.isRunning(): self.recorder.terminate()
        if self.worker.isRunning(): self.worker.terminate()
        ConfigManager.save_config(self.config) # 退出前保存
        self.close()
        self.closed_signal.emit()