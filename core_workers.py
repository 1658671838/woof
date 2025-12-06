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

# --- 配置区域 (黄金比例) ---
# 录制 2 秒：保证实时性，说完话马上出字
CHUNK_DURATION = 2.0
# 重叠 1.5 秒：极大的重叠率，保证长难句不断裂，且能利用上下文
OVERLAP_DURATION = 1.5

CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION)
OVERLAP_SAMPLES = int(SAMPLE_RATE * OVERLAP_DURATION)

# 全局音频队列
audio_queue = queue.Queue(maxsize=10)

# --- 🚫 幻觉词黑名单 ---
BANNED_PHRASES = [
    "字幕", "订阅", "微信", "QQ", "上传", "版权", 
    "观看", "收看", "频道", "点赞", "作者", "视频",
    "Amara.org", "Subtitle", "caption", "社区", "谢谢",
    "李宗盛", "作词", "作曲"
]

# --- 文本比对算法 (用于从重叠音频中提取新内容) ---
def get_new_content(last_text, current_text):
    """
    比较两段文本，返回 current_text 中相对于 last_text 的新增部分。
    """
    if not last_text: return current_text
    if not current_text: return ""
    
    # 如果完全包含，说明还在重复上一句，没新词
    if current_text in last_text: return ""
    if last_text in current_text: 
        # 如果新句子包含了旧句子，只返回多出来的部分
        return current_text.replace(last_text, "")
        
    # 使用序列匹配找重叠
    matcher = difflib.SequenceMatcher(None, last_text, current_text)
    match = matcher.find_longest_match(0, len(last_text), 0, len(current_text))
    
    # 只有当重叠部分在旧句子的结尾，且在新句子的开头时，才认为是有效重叠
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
                    # 录制 2 秒
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
        self.prev_audio = np.array([], dtype=np.float32)
        self.last_full_text = "" # 记录上一轮完整的识别结果

    def run(self):
        try:
            model_size = self.config["model_size"]
            download_root = self.config["model_path"] or os.getcwd()
            save_log = self.config["save_log"]
            log_file = os.path.join(self.config["log_path"], "subtitle_export.txt")

            self.update_text_signal.emit(f"正在加载 {model_size}...")
            
            # 加载模型
            model = WhisperModel(model_size, device="cuda", compute_type="float16", download_root=download_root)
            self.update_text_signal.emit("✅ 极速引擎就绪")
            
            while True:
                try:
                    new_audio = audio_queue.get()
                except:
                    continue
                
                # --- 1. 拼接音频 (滑动窗口) ---
                if len(self.prev_audio) > 0:
                    # 拼接：上一段的尾巴 + 这一段
                    input_audio = np.concatenate((self.prev_audio, new_audio))
                else:
                    input_audio = new_audio
                
                # 保留这一段的尾部给下一次用
                # 我们录了2秒，重叠1.5秒，所以保留最后1.5秒
                self.prev_audio = new_audio[-OVERLAP_SAMPLES:]

                # --- 2. 识别 ---
                try:
                    # 开启 VAD，且不过分依赖上下文（防止幻觉）
                    segments, info = model.transcribe(
                        input_audio, 
                        language="zh", 
                        beam_size=5,
                        vad_filter=True, # 必须开，防幻觉
                        vad_parameters=dict(min_silence_duration_ms=500),
                        condition_on_previous_text=False 
                    )
                    
                    for segment in segments:
                        text = segment.text.strip()
                        
                        # 过滤
                        if len(text) < 1: continue
                        if any(banned in text for banned in BANNED_PHRASES): continue

                        # --- 3. 提取新内容 ---
                        # 这一步至关重要：因为音频重叠了，字肯定会重复
                        # 我们只提取“相对于上一轮新增的字”
                        new_content = get_new_content(self.last_full_text, text)
                        
                        if not new_content: continue # 如果没新词，跳过

                        # 繁简转换
                        simple_text = zhconv.convert(new_content, 'zh-cn')
                        self.update_text_signal.emit(simple_text)
                        
                        # 更新上一轮完整文本记录
                        # 注意：这里要更新成当前识别出的完整 text，而不是 new_content
                        # 这样下一轮才能正确比对
                        self.last_full_text = text 
                        
                        if save_log:
                            t = time.strftime("%H:%M:%S")
                            with open(log_file, "a", encoding="utf-8") as f:
                                f.write(f"[{t}] {simple_text}\n")
                                
                except Exception as e:
                    print(f"推理警告: {e}")

        except Exception as e:
            self.update_text_signal.emit(f"❌ 错误: {str(e)}")