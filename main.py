import sys
from PyQt6.QtWidgets import QApplication
from core_utils import setup_logging, register_nvidia_dlls
from ui_launcher import LauncherWindow

if __name__ == "__main__":
    # 1. 注册日志和DLL修复
    setup_logging()
    register_nvidia_dlls()
    
    # 2. 启动应用
    app = QApplication(sys.argv)
    launcher = LauncherWindow()
    launcher.show()
    sys.exit(app.exec())