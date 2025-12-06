import sys
import os
import time
import queue  # 引入队列库，用于线程间通信
import soundcard as sc
import numpy as np
import zhconv  # 引入繁简转换库
from collections import deque
from pathlib import Path

# 图形界面库
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QPushButton, QHBoxLayout, QFrame
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPoint
from PyQt6.QtGui import QFont, QColor

# AI 模型库
from faster_whisper import WhisperModel

# --- 全局配置 ---
MODEL_SIZE = "medium"    
RECORD_SECONDS = 3       # 每次切片长度
SAMPLE_RATE = 16000      
FONT_SIZE = 24           
TEXT_COLOR = "#00FF7F"   # 改成 SpringGreen 这种亮绿色，看字更清楚

# ================= 🚑 DLL 自动修复 =================
def register_nvidia_dlls():
    try:
        site_packages = Path(sys.prefix) / "Lib" / "site-packages"
        nvidia_path = site_packages / "nvidia"
        if nvidia_path.exists():
            for file in nvidia_path.rglob("*.dll"):
                try:
                    os.add_dll_directory(str(file.parent))
                    os.environ['PATH'] = str(file.parent) + os.pathsep + os.environ['PATH']
                except: pass
    except: pass
register_nvidia_dlls()
# ===================================================

# --- 全局队列：连接“耳朵”和“大脑”的仓库 ---
# maxsize=5 表示最多存5段音频，防止堆积太多导致延迟过大
audio_queue = queue.Queue(maxsize=5)

# --- 线程 1：录音线程 (耳朵) ---
# 它的任务很简单：只管录，录完了扔进队列，绝不休息
class AudioRecorderThread(QThread):
    def run(self):
        default_speaker = sc.default_speaker()
        try:
            mic = sc.get_microphone(id=str(default_speaker.name), include_loopback=True)
        except:
            mic = sc.all_microphones(include_loopback=True)[0]
        
        # 持续录音循环
        with mic.recorder(samplerate=SAMPLE_RATE) as recorder:
            while True:
                # 录制一段音频
                data = recorder.record(numframes=SAMPLE_RATE * RECORD_SECONDS)
                data = data.mean(axis=1).squeeze() # 转单声道
                
                # 如果队列满了，就先把最旧的扔掉，保证实时性（防止延迟越来越高）
                if audio_queue.full():
                    try:
                        audio_queue.get_nowait()
                    except: pass
                
                # 塞进仓库
                audio_queue.put(data)

# --- 线程 2：推理线程 (大脑) ---
# 它的任务：从队列拿音频 -> 识别 -> 转简体 -> 发给界面
class WhisperWorkerThread(QThread):
    update_text_signal = pyqtSignal(str) # 发送给界面的信号

    def run(self):
        print(f"🚀 AI 线程启动，加载模型 {MODEL_SIZE}...")
        try:
            model = WhisperModel(MODEL_SIZE, device="cuda", compute_type="float16")
            self.update_text_signal.emit("✅ 模型就绪，等待音频...")
        except Exception as e:
            self.update_text_signal.emit(f"模型报错: {e}")
            return

        history = deque(maxlen=3) # 用于去重

        while True:
            # 从队列里取数据，如果队列空了就阻塞等待
            audio_data = audio_queue.get()
            
            try:
                segments, info = model.transcribe(
                    audio_data, 
                    language="zh", 
                    beam_size=5,
                    condition_on_previous_text=False
                )

                for segment in segments:
                    text = segment.text.strip()
                    if len(text) > 1 and text not in history:
                        # 1. 繁体转简体 (关键步骤)
                        simple_text = zhconv.convert(text, 'zh-cn')
                        
                        # 2. 发送给界面
                        self.update_text_signal.emit(simple_text)
                        
                        # 3. 记录日志
                        t = time.strftime("%H:%M:%S")
                        with open("subtitle_log.txt", "a", encoding="utf-8") as f:
                            f.write(f"[{t}] {simple_text}\n")
                        
                        history.append(text) # 记录原始文本去重
                        
            except Exception as e:
                print(f"识别出错: {e}")

# --- 主界面：可拖动、带按钮、显示多行 ---
class SubtitleWindow(QWidget):
    def __init__(self):
        super().__init__()
        
        # 1. 窗口基础设置
        self.setWindowTitle("Whisper 字幕")
        self.resize(1200, 180) 
        
        # 去边框 + 置顶 + 工具窗口
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |       
            Qt.WindowType.WindowStaysOnTopHint |      
            Qt.WindowType.Tool                        
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # 【重要改动】取消了鼠标穿透，因为我们要点关闭按钮和拖动窗口
        # self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) <--- 删掉了这行

        # 2. 界面布局
        # 我们用一个 Frame 把所有东西包起来，方便做圆角背景
        self.container = QFrame(self)
        self.container.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(0, 0, 0, 160); /* 背景稍微深一点 */
                border-radius: 20px;
            }}
        """)
        
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.container)
        main_layout.setContentsMargins(0, 0, 0, 0) # 去掉外边距

        # 容器内部布局
        container_layout = QVBoxLayout(self.container)

        # --- 顶部栏：包含关闭按钮 ---
        top_bar = QHBoxLayout()
        top_bar.addStretch() # 弹簧，把按钮顶到右边
        
        # 关闭按钮
        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # 按钮样式：平时透明，鼠标放上去变红
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: white;
                font-size: 20px;
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                background-color: #ff4444;
                border-radius: 15px;
            }
        """)
        self.close_btn.clicked.connect(self.close_app) # 点击触发关闭
        top_bar.addWidget(self.close_btn)
        
        container_layout.addLayout(top_bar)

        # --- 字幕显示区域 ---
        self.label = QLabel("正在启动双线程引擎...", self)
        self.label.setFont(QFont("Microsoft YaHei UI", FONT_SIZE, QFont.Weight.Bold))
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True) # 允许自动换行
        
        # 文字样式
        self.label.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_COLOR};
                /* 文字阴影，增强对比度 */
                qproperty-alignment: AlignCenter;
            }}
        """)
        container_layout.addWidget(self.label)
        container_layout.addStretch() # 底部加个弹簧，让字往上靠一点

        # 3. 移动到屏幕下方
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - self.width()) // 2, screen.height() - 250)

        # 4. 启动双线程
        # 线程A：录音
        self.recorder_thread = AudioRecorderThread()
        self.recorder_thread.start()
        
        # 线程B：识别
        self.worker_thread = WhisperWorkerThread()
        self.worker_thread.update_text_signal.connect(self.update_subtitle)
        self.worker_thread.start()

        # 用于存储最近显示的文本行，防止只能看到一行
        self.text_buffer = deque(maxlen=2) # 只保留最近2句

    def update_subtitle(self, text):
        # 把新的一句加入缓存
        self.text_buffer.append(text)
        # 把缓存里的句子用换行符拼起来显示
        display_text = "\n".join(self.text_buffer)
        self.label.setText(display_text)

    # --- 实现拖动窗口的魔法 ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()
            
    def close_app(self):
        # 优雅退出
        print("正在关闭...")
        QApplication.quit()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SubtitleWindow()
    window.show()
    sys.exit(app.exec())