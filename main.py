import sys
import os
import time
import queue
import json
import traceback  # 引入堆栈追踪库
import soundcard as sc
import zhconv
from collections import deque
from pathlib import Path

# 图形界面库
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout, QPushButton, 
                             QHBoxLayout, QFrame, QComboBox, QFileDialog, QCheckBox, 
                             QLineEdit, QGroupBox, QMessageBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

# AI 模型库
from faster_whisper import WhisperModel

# --- 全局常量 ---
SAMPLE_RATE = 16000
CONFIG_FILE = "config.json"
LOG_FILE = "crash_report.txt" # 崩溃日志文件

# ================= 🚑 错误拦截系统 =================
# 将所有的报错（stderr）重定向到文件里，这样闪退也能看到原因
def log_exception(exc_type, exc_value, exc_traceback):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        t = time.strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"\n[{t}] 💥 致命错误捕获:\n")
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
    # 同时在控制台打印
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

sys.excepthook = log_exception
# ===================================================

# ================= 🚑 DLL 自动修复 =================
def register_nvidia_dlls():
    try:
        # 1. 开发环境路径
        site_packages = Path(sys.prefix) / "Lib" / "site-packages"
        nvidia_path = site_packages / "nvidia"
        
        # 2. 打包后路径 (PyInstaller 的 _internal 文件夹)
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
            nvidia_path = Path(base_path) / "nvidia"
        
        if nvidia_path.exists():
            for file in nvidia_path.rglob("*.dll"):
                try:
                    os.add_dll_directory(str(file.parent))
                    os.environ['PATH'] = str(file.parent) + os.pathsep + os.environ['PATH']
                except: pass
    except: pass
register_nvidia_dlls()
# ===================================================

# --- 配置管理 ---
class ConfigManager:
    @staticmethod
    def load_config():
        default_config = {
            "model_size": "medium",
            "model_path": os.getcwd(),
            "save_log": True,
            "log_path": os.getcwd()
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return {**default_config, **json.load(f)}
            except:
                return default_config
        return default_config

    @staticmethod
    def save_config(config):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)

# --- 线程：录音 ---
class AudioRecorderThread(QThread):
    def run(self):
        global audio_queue
        audio_queue = queue.Queue(maxsize=5)
        
        # 增加一步：检测有没有声卡，没有就报错
        try:
            default_speaker = sc.default_speaker()
            mic = sc.get_microphone(id=str(default_speaker.name), include_loopback=True)
        except Exception as e:
            # 如果找不到内录设备，尝试兜底
            try:
                mic = sc.all_microphones(include_loopback=True)[0]
            except Exception as e2:
                raise RuntimeError(f"无法找到内录设备，请检查声卡驱动: {e2}")

        with mic.recorder(samplerate=SAMPLE_RATE) as recorder:
            while True:
                data = recorder.record(numframes=SAMPLE_RATE * 3)
                data = data.mean(axis=1).squeeze()
                if audio_queue.full():
                    try: audio_queue.get_nowait()
                    except: pass
                audio_queue.put(data)

# --- 线程：推理 ---
class WhisperWorkerThread(QThread):
    update_text_signal = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config

    def run(self):
        try:
            model_size = self.config["model_size"]
            download_root = self.config["model_path"]
            save_log = self.config["save_log"]
            log_dir = self.config["log_path"]

            self.update_text_signal.emit(f"正在加载 {model_size}...")
            
            # 这里的 download_root 如果是空字符串会报错，做一个保护
            if not download_root: download_root = os.getcwd()
            
            model = WhisperModel(model_size, device="cuda", compute_type="float16", download_root=download_root)
            self.update_text_signal.emit("✅ 模型就绪")
            
            history = deque(maxlen=3)
            log_file = os.path.join(log_dir, "subtitle_export.txt")

            while True:
                if 'audio_queue' not in globals(): 
                    time.sleep(0.5)
                    continue
                    
                audio_data = audio_queue.get()
                
                try:
                    segments, info = model.transcribe(audio_data, language="zh", beam_size=5, condition_on_previous_text=False)
                    for segment in segments:
                        text = segment.text.strip()
                        if len(text) > 1 and text not in history:
                            simple_text = zhconv.convert(text, 'zh-cn')
                            self.update_text_signal.emit(simple_text)
                            
                            if save_log:
                                t = time.strftime("%H:%M:%S")
                                with open(log_file, "a", encoding="utf-8") as f:
                                    f.write(f"[{t}] {simple_text}\n")
                            
                            history.append(text)
                except Exception as e:
                    print(f"识别警告: {e}")

        except Exception as e:
            # 将线程内的致命错误发送回主界面
            self.update_text_signal.emit(f"❌ 内部错误: {str(e)}")
            # 并写入日志
            log_exception(type(e), e, e.__traceback__)

# --- 界面 1：启动器 ---
class LauncherWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Whisper 字幕启动器")
        self.resize(500, 400)
        self.config = ConfigManager.load_config()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        
        # 模型设置
        group_model = QGroupBox("🧠 模型设置")
        layout_m = QVBoxLayout()
        layout_m.addWidget(QLabel("选择模型大小:"))
        self.combo_size = QComboBox()
        self.combo_size.addItems(["tiny", "base", "small", "medium", "large-v3"])
        self.combo_size.setCurrentText(self.config["model_size"])
        layout_m.addWidget(self.combo_size)

        layout_m.addWidget(QLabel("模型缓存位置:"))
        h_layout_path = QHBoxLayout()
        self.input_model_path = QLineEdit(self.config["model_path"])
        btn_model_path = QPushButton("📂")
        btn_model_path.clicked.connect(lambda: self.select_folder(self.input_model_path))
        h_layout_path.addWidget(self.input_model_path)
        h_layout_path.addWidget(btn_model_path)
        layout_m.addLayout(h_layout_path)
        group_model.setLayout(layout_m)
        layout.addWidget(group_model)

        # 导出设置
        group_save = QGroupBox("💾 导出设置")
        layout_s = QVBoxLayout()
        self.check_save = QCheckBox("保存字幕文件")
        self.check_save.setChecked(self.config["save_log"])
        layout_s.addWidget(self.check_save)
        
        layout_s.addWidget(QLabel("保存位置:"))
        h_layout_save = QHBoxLayout()
        self.input_log_path = QLineEdit(self.config["log_path"])
        btn_log_path = QPushButton("📂")
        btn_log_path.clicked.connect(lambda: self.select_folder(self.input_log_path))
        h_layout_save.addWidget(self.input_log_path)
        h_layout_save.addWidget(btn_log_path)
        layout_s.addLayout(h_layout_save)
        group_save.setLayout(layout_s)
        layout.addWidget(group_save)

        # 启动按钮
        self.btn_start = QPushButton("🚀 启动字幕")
        self.btn_start.setFixedHeight(50)
        self.btn_start.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.btn_start.clicked.connect(self.start_app)
        layout.addWidget(self.btn_start)
        self.setLayout(layout)

    def select_folder(self, line_edit):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder: line_edit.setText(folder)

    def start_app(self):
        # 1. 检查路径是否为空
        if not self.input_model_path.text().strip():
            self.input_model_path.setText(os.getcwd())
        
        # 2. 保存配置
        new_config = {
            "model_size": self.combo_size.currentText(),
            "model_path": self.input_model_path.text(),
            "save_log": self.check_save.isChecked(),
            "log_path": self.input_log_path.text()
        }
        ConfigManager.save_config(new_config)
        
        # 3. 关键修改：不要 close() 启动器，而是 hide()
        # 这样主程序流不会断，防止闪退
        self.hide()
        
        # 4. 实例化主窗口
        try:
            self.main_window = SubtitleWindow(new_config)
            self.main_window.show()
            # 连接主窗口的关闭信号，主窗口关闭时，真正退出程序
            self.main_window.closed_signal.connect(self.close)
        except Exception as e:
            QMessageBox.critical(self, "启动失败", f"初始化出错:\n{e}")
            self.show() # 出错就显示回来

# --- 界面 2：字幕悬浮窗 ---
class SubtitleWindow(QWidget):
    closed_signal = pyqtSignal() # 自定义信号

    def __init__(self, config):
        super().__init__()
        self.config = config
        
        self.setWindowTitle("Whisper 字幕")
        self.resize(1000, 150)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.container = QFrame(self)
        self.container.setStyleSheet("background-color: rgba(0, 0, 0, 160); border-radius: 20px;")
        
        layout = QVBoxLayout(self)
        layout.addWidget(self.container)
        layout.setContentsMargins(0, 0, 0, 0)
        
        inner_layout = QVBoxLayout(self.container)
        
        # 顶部栏
        top_bar = QHBoxLayout()
        top_bar.addStretch()
        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.setStyleSheet("QPushButton{color:white; background:transparent; font-size:20px; font-weight:bold;} QPushButton:hover{background:#ff4444; border-radius:15px;}")
        self.close_btn.clicked.connect(self.close_app)
        top_bar.addWidget(self.close_btn)
        inner_layout.addLayout(top_bar)

        self.label = QLabel("正在初始化...", self)
        font = self.label.font(); font.setPointSize(24); font.setBold(True)
        self.label.setFont(font)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        self.label.setStyleSheet("color: #00FF7F;")
        inner_layout.addWidget(self.label)
        inner_layout.addStretch()

        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - self.width()) // 2, screen.height() - 250)

        # 启动线程
        self.recorder = AudioRecorderThread()
        self.recorder.start()
        
        self.worker = WhisperWorkerThread(config)
        self.worker.update_text_signal.connect(self.update_text)
        self.worker.start()
        
        self.text_buffer = deque(maxlen=2)

    def update_text(self, text):
        # 收到报错信息直接弹窗
        if text.startswith("❌"):
            self.label.setText(text)
            self.label.setStyleSheet("color: #FF4444;")
        else:
            self.text_buffer.append(text)
            self.label.setText("\n".join(self.text_buffer))
            self.label.setStyleSheet("color: #00FF7F;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()

    def close_app(self):
        # 停止线程
        if self.recorder.isRunning(): self.recorder.terminate()
        if self.worker.isRunning(): self.worker.terminate()
        self.close()
        self.closed_signal.emit() # 通知启动器可以关门了

if __name__ == "__main__":
    # 强制清理之前的日志
    if os.path.exists(LOG_FILE): os.remove(LOG_FILE)
    
    app = QApplication(sys.argv)
    launcher = LauncherWindow()
    launcher.show()
    sys.exit(app.exec())