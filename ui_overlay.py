import sys
from collections import deque
from PyQt6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QPushButton, QHBoxLayout, 
                             QFrame, QApplication, QSizeGrip, QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QFont, QCursor, QFontMetrics
from core_workers import AudioRecorderThread, WhisperWorkerThread
from core_utils import ConfigManager

class ResizableSubtitleWindow(QWidget):
    closed_signal = pyqtSignal()
    MARGIN = 10 # 边缘拖拽判定距离

    def __init__(self, config):
        super().__init__()
        self.config = config
        
        # 1. 基础窗口属性
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        
        # 2. 恢复尺寸
        w = config.get("window_width", 1000)
        h = config.get("window_height", 200) # 默认稍微高一点
        self.resize(w, h)
        
        # 居中
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - self.width()) // 2, screen.height() - 300)

        # 3. 初始化 UI
        self.setup_ui()
        
        # 4. 关键：历史记录缓存扩大
        # 之前是 maxlen=2，现在改成 50，这样拉大窗口时能看到历史
        self.text_buffer = deque(maxlen=50) 
        
        # 5. 启动线程
        self.start_threads()
        
        # 状态变量
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
        inner_layout.setContentsMargins(15, 10, 15, 15) # 设置内边距，防止文字贴边
        
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
        
        # --- 字幕显示 Label ---
        self.label = QLabel("Waiting for audio...", self)
        
        # 设置字体
        font_size = self.config.get("font_size", 24)
        self.current_font = QFont("Microsoft YaHei UI", font_size)
        self.current_font.setBold(True)
        self.label.setFont(self.current_font)
        
        # 关键设置
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom) # 靠左、靠下对齐
        self.label.setWordWrap(True) # 允许自动换行
        self.label.setStyleSheet("color: #00FF7F; border: none;") # 亮绿色字体
        
        # 放入布局，并设置拉伸因子，让 Label 占据主要空间
        inner_layout.addWidget(self.label, 1)

        # 右下角拖拽手柄
        self.size_grip = QSizeGrip(self.container)
        self.size_grip.setStyleSheet("background-color: transparent;") 

    def start_threads(self):
        self.recorder = AudioRecorderThread()
        self.recorder.start()
        
        self.worker = WhisperWorkerThread(self.config)
        self.worker.update_text_signal.connect(self.add_text) # 改名为 add_text
        self.worker.start()

    # --- 核心逻辑：添加文本并刷新 ---
    def add_text(self, text):
        if text.startswith("❌"):
            self.label.setText(text)
            self.label.setStyleSheet("color: #FF4444;")
        else:
            self.label.setStyleSheet("color: #00FF7F;")
            # 加入缓存
            self.text_buffer.append(text)
            # 刷新显示
            self.refresh_display_content()

    # --- 核心逻辑：计算该显示多少行 ---
    def refresh_display_content(self):
        if not self.text_buffer: return

        # 1. 获取字体高度
        fm = QFontMetrics(self.current_font)
        line_height = fm.lineSpacing() + 5 # 行高 + 这里的5是行间距缓冲
        
        # 2. 获取 Label 可用的显示高度
        # 减去顶部栏的大概高度(30)和边距(25)
        available_height = self.container.height() - 55 
        
        # 3. 计算能塞下多少行
        max_lines_possible = max(1, available_height // line_height)
        
        # 4. 从缓存中截取最后 N 行
        # 注意：这里是按“句子”截取的。如果一句话太长换行了，Qt Label 会自动处理
        # 为了防止文字溢出，我们稍微保守一点，取 max_lines_possible 个句子
        lines_to_show = list(self.text_buffer)[-max_lines_possible:]
        
        # 5. 更新文本
        display_text = "\n".join(lines_to_show)
        self.label.setText(display_text)

    # --- 窗口大小改变事件 ---
    def resizeEvent(self, event):
        # 1. 保存尺寸配置
        self.config["window_width"] = self.width()
        self.config["window_height"] = self.height()
        
        # 2. 调整手柄位置
        self.size_grip.move(self.width() - 20, self.height() - 20)
        
        # 3. 重新计算应该显示多少行文字
        self.refresh_display_content()
        
        super().resizeEvent(event)

    # --- 鼠标拖拽逻辑 (保持不变) ---
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
        print("正在停止后台线程，请稍候...")
        
        # 1. 优雅地停止线程（不再使用暴力的 terminate）
        if hasattr(self, 'recorder'):
            self.recorder.stop()
        
        if hasattr(self, 'worker'):
            self.worker.stop()
            
        # 2. 保存配置
        ConfigManager.save_config(self.config)
        
        # 3. 关闭窗口
        self.close()
        self.closed_signal.emit()