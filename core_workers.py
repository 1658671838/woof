import time
import queue
import os
import soundcard as sc
import zhconv
from collections import deque
from PyQt6.QtCore import QThread, pyqtSignal
from faster_whisper import WhisperModel
from core_utils import SAMPLE_RATE

# 全局音频队列
audio_queue = queue.Queue(maxsize=5)

# --- 耳朵：录音线程 ---
class AudioRecorderThread(QThread):
    def __init__(self):
        super().__init__()
        self.is_running = True # 🛑 新增：运行状态标志

    def run(self):
        global audio_queue
        audio_queue = queue.Queue(maxsize=5)
        
        try:
            default_speaker = sc.default_speaker()
            mic = sc.get_microphone(id=str(default_speaker.name), include_loopback=True)
        except:
            try: mic = sc.all_microphones(include_loopback=True)[0]
            except: return 

        with mic.recorder(samplerate=SAMPLE_RATE) as recorder:
            # 🛑 修改：不再是 while True，而是检查标志位
            while self.is_running:
                # 录制 3 秒
                try:
                    data = recorder.record(numframes=SAMPLE_RATE * 3)
                    data = data.mean(axis=1).squeeze()
                    if audio_queue.full():
                        try: audio_queue.get_nowait()
                        except: pass
                    audio_queue.put(data)
                except Exception as e:
                    print(f"录音中断: {e}")
                    break

    # 🛑 新增：停止方法
    def stop(self):
        self.is_running = False
        self.wait() # 等待线程安全结束

# --- 大脑：AI 线程 ---
class WhisperWorkerThread(QThread):
    update_text_signal = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.is_running = True # 🛑 新增

    def run(self):
        try:
            model_size = self.config["model_size"]
            download_root = self.config["model_path"] or os.getcwd()
            save_log = self.config["save_log"]
            log_file = os.path.join(self.config["log_path"], "subtitle_export.txt")

            self.update_text_signal.emit(f"正在加载 {model_size}...")
            
            model = WhisperModel(model_size, device="cuda", compute_type="float16", download_root=download_root)
            self.update_text_signal.emit("✅ 模型就绪")
            
            history = deque(maxlen=3)

            # 🛑 修改：检查标志位
            while self.is_running:
                # 如果队列空了，就休息一会，不要死循环空转
                try:
                    # timeout=1 表示等1秒，如果还没有数据就抛出Empty异常，继续下一轮循环检查 is_running
                    audio_data = audio_queue.get(timeout=1) 
                except queue.Empty:
                    continue
                
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
                    print(f"推理警告: {e}")

        except Exception as e:
            self.update_text_signal.emit(f"❌ 错误: {str(e)}")

    # 🛑 新增：停止方法
    def stop(self):
        self.is_running = False
        self.wait()