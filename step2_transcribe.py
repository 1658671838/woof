import soundcard as sc
import numpy as np
from faster_whisper import WhisperModel
import time

# --- 配置区域 ---
# 模型大小：建议 RTX 5070 使用 "medium" 或 "large-v3"
# 可选值: tiny, base, small, medium, large-v3
MODEL_SIZE = "small" 
RECORD_SECONDS = 3  # 每次录几秒（太短了识别不准，太长了延迟高）
SAMPLE_RATE = 16000 # Whisper 固定的标准采样率

def main():
    print(f"🔄 正在加载 Whisper 模型 ({MODEL_SIZE})...")
    # 1. 加载模型到显卡
    # compute_type="float16" 是显卡加速的关键
    model = WhisperModel(MODEL_SIZE, device="cuda", compute_type="float16")
    print("✅ 模型加载完毕！")

    # 2. 获取内录设备 (复制上一关的逻辑)
    default_speaker = sc.default_speaker()
    try:
        mic = sc.get_microphone(id=str(default_speaker.name), include_loopback=True)
    except:
        mic = sc.all_microphones(include_loopback=True)[0]
    
    print(f"🎧 正在监听: {default_speaker.name}")
    print("---------------------------------------")
    print("请播放中文视频 (B站/爱奇艺)...")
    print("按 Ctrl+C 停止")
    print("---------------------------------------")

    with mic.recorder(samplerate=SAMPLE_RATE) as recorder:
        while True:
            # 3. 录音
            # numframes = 采样率 * 秒数
            data = recorder.record(numframes=SAMPLE_RATE * RECORD_SECONDS)
            
            # 4. 数据预处理 (关键原理！)
            # soundcard 录下来的是“立体声”(双声道)，数据形状是 [N, 2]
            # Whisper 模型只吃“单声道”数据。
            # 我们把两个声道的数据取平均值，合并成一个声道。
            # squeeze() 是为了把多余的维度压缩掉，变成纯粹的一维数组。
            data = data.mean(axis=1).squeeze()

            # 5. 开始识别 (Inference)
            # language="zh": 强制指定中文，防止它瞎猜
            segments, info = model.transcribe(data, language="zh", beam_size=5)

            # 6. 打印结果
            # segments 是一个生成器，我们需要遍历它才能拿到文本
            for segment in segments:
                # 过滤掉空的或者幻觉内容
                if segment.text.strip():
                    print(f"📝 识别结果: {segment.text}")
                    
                    # 顺手实现你的“导出”需求
                    with open("subtitle_log.txt", "a", encoding="utf-8") as f:
                        timestamp = time.strftime("%H:%M:%S")
                        f.write(f"[{timestamp}] {segment.text}\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 停止识别。")