import os
import sys
from pathlib import Path

def find_and_register_dll():
    print("🕵️ 正在地毯式搜索 cublas64_12.dll ...")
    
    # 1. 确定搜索范围：你的 Python 安装目录下的 site-packages
    # 根据你的报错日志，你的库应该在这里：
    site_packages = Path(sys.prefix) / "Lib" / "site-packages"
    print(f"📂 搜索目录: {site_packages}")

    # 2. 查找文件
    # rglob 是递归查找，它会翻遍所有子文件夹
    found_files = list(site_packages.rglob("cublas64_12.dll"))

    if not found_files:
        print("❌ 完蛋，根本没找到文件！可能安装未成功。")
        print("尝试重新运行: pip install --force-reinstall nvidia-cublas-cu12")
        return

    # 3. 找到后，把它的文件夹加入到系统路径
    dll_path = found_files[0]
    dll_dir = dll_path.parent
    print(f"✅ 找到了！文件藏在这里:\n   {dll_path}")
    
    # 4. 暴力注册路径 (两种方法一起用，确保万无一失)
    try:
        # 方法 A: Python 3.8+ 专用方法
        os.add_dll_directory(str(dll_dir))
        print("   -> 已通过 os.add_dll_directory 注册")
    except Exception as e:
        print(f"   -> add_dll_directory 失败: {e}")

    # 方法 B: 传统的环境变量方法
    os.environ['PATH'] = str(dll_dir) + os.pathsep + os.environ['PATH']
    print("   -> 已将路径加入系统环境变量 PATH")

    # 5. 顺便找一下 cudnn (防止待会儿报下一个错)
    cudnn_files = list(site_packages.rglob("cudnn_ops_infer64_8.dll"))
    if cudnn_files:
        cudnn_dir = cudnn_files[0].parent
        os.add_dll_directory(str(cudnn_dir))
        os.environ['PATH'] = str(cudnn_dir) + os.pathsep + os.environ['PATH']
        print(f"✅ 也找到了 cuDNN 库，已一并注册: {cudnn_dir}")

    print("\n🚀 正在尝试在当前脚本中加载模型测试...")
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("tiny", device="cuda", compute_type="float16")
        print("\n🎉🎉🎉 成功了！模型已成功加载！DLL 问题解决！")
    except Exception as e:
        print(f"\n❌ 依然报错: {e}")
        # 如果还是报错，可能是缺 zlibwapi.dll
        if "zlibwapi" in str(e) or "126" in str(e):
             print("💡 看起来可能还需要 zlibwapi.dll，这是另一个常见坑。")

if __name__ == "__main__":
    find_and_register_dll()