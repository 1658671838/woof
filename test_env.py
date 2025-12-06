import torch
import faster_whisper
import soundcard
import PyQt6
from faster_whisper import WhisperModel

print("------- 环境自检报告 -------")

# 1. 检查 PyTorch 是否能看到显卡
if torch.cuda.is_available():
    print(f"✅ PyTorch 成功检测到显卡: {torch.cuda.get_device_name(0)}")
    print(f"   CUDA 版本: {torch.version.cuda}")
else:
    print("❌ PyTorch 未检测到显卡，请检查第二步安装是否正确！")

# 2. 检查 faster-whisper 是否能调用显卡
try:
    # 尝试加载一个小模型，指定 device="cuda"
    print("🔄 正在测试 Whisper 模型加载 (第一次运行会下载模型，请稍候)...")
    # 我们用 tiny 模型做测试，因为它非常小，下载很快
    model = WhisperModel("tiny", device="cuda", compute_type="float16")
    print("✅ Faster-Whisper 成功在 GPU 上加载！")
except Exception as e:
    print(f"❌ Faster-Whisper 加载失败: {e}")
    print("   (如果报错提示缺少 dll，可能需要检查 cuDNN 路径)")

print("------- 检查结束 -------")