import sys
import os
import json
import time
import traceback
from pathlib import Path

# --- 全局常量 ---
CONFIG_FILE = "config.json"
LOG_FILE = "crash_report.txt"
SAMPLE_RATE = 16000

# 1. 错误拦截与日志
def setup_logging():
    def log_exception(exc_type, exc_value, exc_traceback):
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            t = time.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"\n[{t}] 💥 致命错误捕获:\n")
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
    sys.excepthook = log_exception

# 2. DLL 修复
def register_nvidia_dlls():
    try:
        site_packages = Path(sys.prefix) / "Lib" / "site-packages"
        nvidia_path = site_packages / "nvidia"
        if getattr(sys, 'frozen', False): # 如果是打包环境
            base_path = sys._MEIPASS
            nvidia_path = Path(base_path) / "nvidia"
        
        if nvidia_path.exists():
            for file in nvidia_path.rglob("*.dll"):
                try:
                    os.add_dll_directory(str(file.parent))
                    os.environ['PATH'] = str(file.parent) + os.pathsep + os.environ['PATH']
                except: pass
    except: pass

# 3. 配置管理
class ConfigManager:
    @staticmethod
    def load_config():
        default = {
            "model_size": "medium",
            "model_path": os.getcwd(),
            "save_log": True,
            "log_path": os.getcwd(),
            "font_size": 24,         # 新增：字体大小记忆
            "window_width": 1000,    # 新增：窗口宽度记忆
            "window_height": 150     # 新增：窗口高度记忆
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return {**default, **json.load(f)}
            except: return default
        return default

    @staticmethod
    def save_config(config):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)