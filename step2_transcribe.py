import os
import sys
from pathlib import Path

# ================= 🚑 自动 DLL 修复模块 (核心) =================
# 这一段会在程序最开始运行，自动帮 faster-whisper 找到显卡驱动
def register_nvidia_dlls():
    try:
        # 1. 定位 site-packages/nvidia 目录
        site_packages = Path(sys.prefix) / "Lib" / "site-packages"
        nvidia_path = site_packages / "nvidia"
        
        if nvidia_path.exists():
            # 2. 遍历下面所有的文件夹，如果是 dll 目录就注册
            # 重点关注 cublas 和 cudnn
            count = 0
            for file in nvidia_path.rglob("*.dll"):
                folder = file.parent
                try:
                    os.add_dll_directory(str(folder))
                    # 同时也加到 PATH 环境变量，双重保险
                    os.environ['PATH'] = str(folder) + os.pathsep + os.environ['PATH']
                    count += 1
                except:
                    pass
            print(f"✅ 已自动注册 Nvidia 运行库路径 (共扫描到 {count} 个位置)")
        else:
            print("⚠️ 未找到 nvidia 库目录，如果运行报错请检查 pip install")
            
    except Exception as e:
        print(f"⚠️ 路径注册出现小问题 (通常可忽略): {e}")

# 执行修复
register_nvidia_dlls()
# =============================================================

import soundcard as sc
import numpy as np
from faster_whisper import WhisperModel
import time
from collections import deque

# --- 配置区域 ---
# 既然显卡修好了，我们用 medium 模型，准确率吊打 small
MODEL_SIZE = "medium" 
# 每次录 4 秒，既能保证句子完整，又不会让延迟太高
RECORD_SECONDS = 4
SAMPLE_RATE = 16000 

def main():
    print(f"\n🚀 正在加载 Whisper 模型 ({MODEL_SIZE})...")
    print("   (第一次运行 medium 模型需要下载约 1.5GB 文件，请耐心等待...)")
    
    try:
        # 显卡加速模式
        model = WhisperModel(MODEL_SIZE, device="cuda", compute_type="float16")
        print("✅ 模型加载完毕！性能状态：火力全开 (GPU)")
    except Exception as e:
        print(f"❌ 致命错误: {e}")
        return

    # 获取内录设备
    default_speaker = sc.default_speaker()
    try:
        mic = sc.get_microphone(id=str(default_speaker.name), include_loopback=True)
    except:
        mic = sc.all_microphones(include_loopback=True)[0]
    
    print(f"🎧 正在监听: {default_speaker.name}")
    print("---------------------------------------")
    print("🎥 请播放 B站/爱奇艺 视频 (中文)...")
    print("📝 字幕将实时打印在下方，并保存到 subtitle_log.txt")
    print("---------------------------------------")

    # 用来存储最近 3 条记录，做简单的去重
    history = deque(maxlen=3)

    with mic.recorder(samplerate=SAMPLE_RATE) as recorder:
        while True:
            # 录音
            data = recorder.record(numframes=SAMPLE_RATE * RECORD_SECONDS)
            # 转单声道
            data = data.mean(axis=1).squeeze()

            # 识别
            try:
                # condition_on_previous_text=False: 防止它在这个切片里产生幻觉重复上一句
                segments, info = model.transcribe(
                    data, 
                    language="zh", 
                    beam_size=5,
                    condition_on_previous_text=False
                )
                
                print("⚡", end="\r") # 闪烁表示正在运算
                
                for segment in segments:
                    text = segment.text.strip()
                    # 简单过滤：如果只有标点符号或者太短，或者是重复的废话，就跳过
                    if len(text) > 1 and text not in history:
                        t = time.strftime("%H:%M:%S")
                        
                        # 打印到屏幕
                        print(f"[{t}] {text}")
                        
                        # 写入文件 (你的导出需求)
                        with open("subtitle_log.txt", "a", encoding="utf-8") as f:
                            f.write(f"[{t}] {text}\n")
                        
                        # 加入历史记录用于去重
                        history.append(text)
                        
            except Exception as e:
                print(f"⚠️ 识别跳过: {e}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 字幕生成已停止。")