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
    def run(self):
        global audio_queue
        # 重新初始化队列
        audio_queue = queue.Queue(maxsize=5)
        
        try:
            default_speaker = sc.default_speaker()
            mic = sc.get_microphone(id=str(default_speaker.name), include_loopback=True)
        except:
            try: mic = sc.all_microphones(include_loopback=True)[0]
            except: return 

        with mic.recorder(samplerate=SAMPLE_RATE) as recorder:
            while True:
                # 录制 3 秒
                data = recorder.record(numframes=SAMPLE_RATE * 3)
                data = data.mean(axis=1).squeeze()
                if audio_queue.full():
                    try: audio_queue.get_nowait()
                    except: pass
                audio_queue.put(data)

# --- 大脑：AI 线程 ---
class WhisperWorkerThread(QThread):
    update_text_signal = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config

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

            while True:
                if audio_queue.empty():
                    time.sleep(0.1)
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
                    print(f"推理警告: {e}")

        except Exception as e:
            self.update_text_signal.emit(f"❌ 错误: {str(e)}")