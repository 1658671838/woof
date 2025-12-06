import sys
import os
import time
import queue
import json
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

# --- 全局常量 ---
SAMPLE_RATE = 16000
CONFIG_FILE = "config.json" # 用于保存用户设置

# --- 工具类：配置管理 ---
class ConfigManager:
    @staticmethod
    def load_config():
        default_config = {
            "model_size": "medium",
            "model_path": os.getcwd(), # 默认下载到当前目录
            "save_log": True,
            "log_path": os.getcwd()
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return {**default_config, **json.load(f)} # 合并默认值，防止缺字段
            except:
                return default_config
        return default_config

    @staticmethod
    def save_config(config):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)

# --- 线程：录音 (耳朵) ---
class AudioRecorderThread(QThread):
    def run(self):
        # 创建一个全局队列用于通信
        global audio_queue
        audio_queue = queue.Queue(maxsize=5)
        
        try:
            default_speaker = sc.default_speaker()
            mic = sc.get_microphone(id=str(default_speaker.name), include_loopback=True)
        except:
            try:
                mic = sc.all_microphones(include_loopback=True)[0]
            except:
                return # 没找到设备，静默失败（会在主线程报错）

        with mic.recorder(samplerate=SAMPLE_RATE) as recorder:
            while True:
                data = recorder.record(numframes=SAMPLE_RATE * 3) # 固定3秒切片
                data = data.mean(axis=1).squeeze()
                if audio_queue.full():
                    try: audio_queue.get_nowait()
                    except: pass
                audio_queue.put(data)

# --- 线程：推理 (大脑) ---
class WhisperWorkerThread(QThread):
    update_text_signal = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config # 接收用户设置

    def run(self):
        model_size = self.config["model_size"]
        download_root = self.config["model_path"]
        save_log = self.config["save_log"]
        log_dir = self.config["log_path"]

        self.update_text_signal.emit(f"正在加载 {model_size} 模型...")
        
        try:
            # download_root 指定模型下载/读取的位置
            model = WhisperModel(model_size, device="cuda", compute_type="float16", download_root=download_root)
            self.update_text_signal.emit("✅ 模型就绪")
        except Exception as e:
            self.update_text_signal.emit(f"加载失败: {e}")
            return

        history = deque(maxlen=3)
        
        # 准备日志文件路径
        log_file = os.path.join(log_dir, "subtitle_export.txt")

        while True:
            if 'audio_queue' not in globals(): 
                time.sleep(1)
                continue
                
            audio_data = audio_queue.get()
            
            try:
                segments, info = model.transcribe(audio_data, language="zh", beam_size=5, condition_on_previous_text=False)
                for segment in segments:
                    text = segment.text.strip()
                    if len(text) > 1 and text not in history:
                        simple_text = zhconv.convert(text, 'zh-cn')
                        self.update_text_signal.emit(simple_text)
                        
                        # 根据设置决定是否保存
                        if save_log:
                            t = time.strftime("%H:%M:%S")
                            with open(log_file, "a", encoding="utf-8") as f:
                                f.write(f"[{t}] {simple_text}\n")
                        
                        history.append(text)
            except Exception as e:
                print(f"Error: {e}")

# --- 界面 1：启动器 (Launcher) ---
class LauncherWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Whisper 字幕启动器")
        self.resize(500, 400)
        self.config = ConfigManager.load_config()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        
        # 1. 模型选择区域
        group_model = QGroupBox("🧠 模型设置")
        layout_m = QVBoxLayout()
        
        # 模型大小下拉框
        layout_m.addWidget(QLabel("选择模型大小 (显存越小选越小的):"))
        self.combo_size = QComboBox()
        self.combo_size.addItems(["tiny", "base", "small", "medium", "large-v3"])
        self.combo_size.setCurrentText(self.config["model_size"])
        layout_m.addWidget(self.combo_size)

        # 模型路径选择
        layout_m.addWidget(QLabel("模型缓存位置:"))
        h_layout_path = QHBoxLayout()
        self.input_model_path = QLineEdit(self.config["model_path"])
        btn_model_path = QPushButton("📂 选择")
        btn_model_path.clicked.connect(lambda: self.select_folder(self.input_model_path))
        h_layout_path.addWidget(self.input_model_path)
        h_layout_path.addWidget(btn_model_path)
        layout_m.addLayout(h_layout_path)
        
        group_model.setLayout(layout_m)
        layout.addWidget(group_model)

        # 2. 导出设置区域
        group_save = QGroupBox("💾 导出设置")
        layout_s = QVBoxLayout()
        
        self.check_save = QCheckBox("保存字幕文件")
        self.check_save.setChecked(self.config["save_log"])
        layout_s.addWidget(self.check_save)
        
        layout_s.addWidget(QLabel("保存位置:"))
        h_layout_save = QHBoxLayout()
        self.input_log_path = QLineEdit(self.config["log_path"])
        btn_log_path = QPushButton("📂 选择")
        btn_log_path.clicked.connect(lambda: self.select_folder(self.input_log_path))
        h_layout_save.addWidget(self.input_log_path)
        h_layout_save.addWidget(btn_log_path)
        layout_s.addLayout(h_layout_save)
        
        group_save.setLayout(layout_s)
        layout.addWidget(group_save)

        # 3. 启动按钮
        self.btn_start = QPushButton("🚀 启动字幕")
        self.btn_start.setFixedHeight(50)
        self.btn_start.setStyleSheet("background-color: #4CAF50; color: white; font-size: 16px; font-weight: bold;")
        self.btn_start.clicked.connect(self.start_app)
        layout.addWidget(self.btn_start)

        self.setLayout(layout)

    def select_folder(self, line_edit):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            line_edit.setText(folder)

    def start_app(self):
        # 更新配置
        new_config = {
            "model_size": self.combo_size.currentText(),
            "model_path": self.input_model_path.text(),
            "save_log": self.check_save.isChecked(),
            "log_path": self.input_log_path.text()
        }
        # 保存到本地，下次自动加载
        ConfigManager.save_config(new_config)
        
        # 打开主窗口，关闭启动器
        self.main_window = SubtitleWindow(new_config)
        self.main_window.show()
        self.close()

# --- 界面 2：字幕悬浮窗 (Subtitle Overlay) ---
class SubtitleWindow(QWidget):
    def __init__(self, config):
        super().__init__()
        self.config = config
        
        # 窗口设置
        self.setWindowTitle("Whisper 字幕")
        self.resize(1000, 150)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 布局
        self.container = QFrame(self)
        self.container.setStyleSheet("background-color: rgba(0, 0, 0, 160); border-radius: 20px;")
        
        layout = QVBoxLayout(self)
        layout.addWidget(self.container)
        layout.setContentsMargins(0, 0, 0, 0)
        
        inner_layout = QVBoxLayout(self.container)
        
        # 顶部按钮栏
        top_bar = QHBoxLayout()
        top_bar.addStretch()
        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.setStyleSheet("QPushButton{color:white; background:transparent; font-size:20px; font-weight:bold;} QPushButton:hover{background:#ff4444; border-radius:15px;}")
        self.close_btn.clicked.connect(self.close_app)
        top_bar.addWidget(self.close_btn)
        inner_layout.addLayout(top_bar)

        # 文本标签
        self.label = QLabel("正在初始化...", self)
        self.label.setFont(self.font())
        font = self.label.font()
        font.setPointSize(24)
        font.setBold(True)
        self.label.setFont(font)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        self.label.setStyleSheet("color: #00FF7F;")
        inner_layout.addWidget(self.label)
        inner_layout.addStretch()

        # 居中显示
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
        self.text_buffer.append(text)
        self.label.setText("\n".join(self.text_buffer))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()

    def close_app(self):
        QApplication.quit()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # 先显示启动器
    launcher = LauncherWindow()
    launcher.show()
    sys.exit(app.exec())