import soundcard as sc
import numpy as np
import time

def main():
    print("正在寻找默认扬声器...")
    # 1. 获取默认扬声器（你平时听歌用的那个）
    default_speaker = sc.default_speaker()
    print(f"🎧 锁定扬声器: {default_speaker.name}")

    print("------------------------------------------------")
    print("请现在打开浏览器，去 B 站或爱奇艺播放一个视频！")
    print("如果下方数值在跳动，说明抓取成功。")
    print("按 Ctrl+C 可以停止程序。")
    print("------------------------------------------------")

    # 2. 获取对应的“内录麦克风”
    # include_loopback=True 是关键，它允许我们看到“系统内部声音”
    try:
        # 大多数 Windows 电脑上，通过扬声器名字就能找到对应的内录设备
        mic = sc.get_microphone(id=str(default_speaker.name), include_loopback=True)
    except Exception as e:
        print("自动匹配失败，尝试使用第一个可用的 Loopback 设备...")
        mics = sc.all_microphones(include_loopback=True)
        # 这是一个兜底策略，取列表里第一个可能是内录的设备
        mic = mics[0] 
    
    # 3. 开始录音循环
    # samplerate=16000 是语音识别的标准采样率
    with mic.recorder(samplerate=16000) as recorder:
        while True:
            # 每次录制 0.5 秒的数据 (8000个采样点)
            data = recorder.record(numframes=8000)
            
            # 4. 计算音量 (均方根 RMS)
            # 简单的数学计算：把声音数据的振幅平方、求平均、开根号
            volume = np.sqrt(np.mean(data**2))
            
            # 打印一个简单的进度条来可视化音量
            bar_length = int(volume * 500) # 放大系数，方便显示
            bar = "█" * bar_length
            
            # \r 让我们在同一行刷新打印，不刷屏
            print(f"\r🔊 实时音量: {volume:.4f} | {bar}", end="")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n程序已停止。")