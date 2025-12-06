import time
import queue
import os
import difflib
import numpy as np
import soundcard as sc
import zhconv
from collections import deque
from PyQt6.QtCore import QThread, pyqtSignal
from faster_whisper import WhisperModel
from core_utils import SAMPLE_RATE

# --- ⚡ 极限配置 ---
# 录制间隔：每 0.5 秒就输出一次！(超快刷新)
RECORD_INTERVAL = 0.5 

# AI 听觉窗口：虽然每0.5秒刷新，但AI每次要听最近 2.5 秒的声音，否则听不懂
AI_WINDOW_SECONDS = 2.5 

# 计算采样点
CHUNK_SAMPLES = int(SAMPLE_RATE * RECORD_INTERVAL)
WINDOW_SAMPLES = int(SAMPLE_RATE * AI_WINDOW_SECONDS)

# 全局音频队列
audio_queue = queue.Queue(maxsize=20)

# --- 🚫 幻觉词黑名单 ---
BANNED_PHRASES = [
    "字幕", "订阅", "微信", "QQ", "上传", "版权", 
    "观看", "收看", "频道", "点赞", "作者", "视频",
    "Amara.org", "Subtitle", "caption", "社区", "谢谢",
    "李宗盛", "作词", "作曲", "大家", "各位"
]

# --- 文本比对算法 (提取增量) ---
def get_new_content(last_text, current_text):
    if not last_text: return current_text
    if not current_text: return ""
    if current_text in last_text: return ""
    if last_text in current_text: return current_text.replace(last_text, "")
    
    matcher = difflib.SequenceMatcher(None, last_text, current_text)
    match = matcher.find_longest_match(0, len(last_text), 0, len(current_text))
    
    if match.size > 1 and match.a + match.size == len(last_text) and match.b == 0:
        return current_text[match.size:]
    return current_text

# --- 耳朵：录音线程 ---
class AudioRecorderThread(QThread):
    def __init__(self):
        super().__init__()
        self.daemon = True 

    def run(self):
        global audio_queue
        with audio_queue.mutex: audio_queue.queue.clear()
        
        try:
            default_speaker = sc.default_speaker()
            mic = sc.get_microphone(id=str(default_speaker.name), include_loopback=True)
        except:
            try: mic = sc.all_microphones(include_loopback=True)[0]
            except: return 

        with mic.recorder(samplerate=SAMPLE_RATE) as recorder:
            while True:
                try:
                    # 极速录制：每 0.5 秒吐出一块肉
                    data = recorder.record(numframes=CHUNK_SAMPLES)
                    data = data.mean(axis=1).squeeze()
                    
                    if audio_queue.full():
                        try: audio_queue.get_nowait()
                        except: pass
                    audio_queue.put(data)
                except Exception:
                    break

# --- 大脑：AI 线程 ---
class WhisperWorkerThread(QThread):
    update_text_signal = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.daemon = True
        # 滚动缓冲区：初始化为空
        self.audio_buffer = np.array([], dtype=np.float32)
        self.last_full_text = "" 

    def run(self):
        try:
            model_size = self.config["model_size"]
            download_root = self.config["model_path"] or os.getcwd()
            save_log = self.config["save_log"]
            log_file = os.path.join(self.config["log_path"], "subtitle_export.txt")

            self.update_text_signal.emit(f"正在加载 {model_size} (极速模式)...")
            
            # 💡 技巧：对于极速模式，small 模型反应比 medium 快，如果觉得 medium 卡可以换 small
            model = WhisperModel(model_size, device="cuda", compute_type="float16", download_root=download_root)
            self.update_text_signal.emit("✅ 极速引擎就绪")
            
            while True:
                try:
                    # 获取最新的 0.5s 音频
                    new_chunk = audio_queue.get()
                except:
                    continue
                
                # --- 1. 滚动缓冲 (Rolling Buffer) ---
                # 把新肉拼到缓冲区后面
                self.audio_buffer = np.concatenate((self.audio_buffer, new_chunk))
                
                # 如果缓冲区太长了，切掉最旧的，只保留最近的 2.5 秒
                # 这样 AI 永远在听“最近发生的 2.5 秒”
                if len(self.audio_buffer) > WINDOW_SAMPLES:
                    self.audio_buffer = self.audio_buffer[-WINDOW_SAMPLES:]

                # --- 2. 识别 ---
                try:
                    # 必须开 VAD，否则静音时会疯狂输出重复词
                    segments, info = model.transcribe(
                        self.audio_buffer, 
                        language="zh", 
                        beam_size=5,
                        vad_filter=True, 
                        vad_parameters=dict(min_silence_duration_ms=300), # 对静音更敏感
                        condition_on_previous_text=False 
                    )
                    
                    # 拼接所有识别结果（因为2.5秒可能包含两句话）
                    current_full_text = "".join([s.text.strip() for s in segments])
                    
                    if not current_full_text: continue
                    if any(banned in current_full_text for banned in BANNED_PHRASES): continue

                    # --- 3. 提取增量 ---
                    # 比如上一轮(0~2.0s)听到 "今天天气"，这一轮(0.5~2.5s)听到 "今天天气不错"
                    # 增量就是 "不错"
                    new_content = get_new_content(self.last_full_text, current_full_text)
                    
                    if not new_content: 
                        # 如果没有新内容，说明还在处理老句子，更新一下缓存即可
                        # 只有当新识别的文字比上次长时，才更新 last_full_text，防止因为切片导致文字变短
                        if len(current_full_text) >= len(self.last_full_text):
                             self.last_full_text = current_full_text
                        continue

                    # 繁简转换
                    simple_text = zhconv.convert(new_content, 'zh-cn')
                    self.update_text_signal.emit(simple_text)
                    
                    # 更新状态
                    self.last_full_text = current_full_text 
                    
                    if save_log:
                        t = time.strftime("%H:%M:%S")
                        with open(log_file, "a", encoding="utf-8") as f:
                            f.write(f"[{t}] {simple_text}\n")
                                
                except Exception as e:
                    print(f"推理警告: {e}")

        except Exception as e:
            self.update_text_signal.emit(f"❌ 错误: {str(e)}")