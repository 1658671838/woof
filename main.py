import sys
import os # 引入 os 库
from PyQt6.QtWidgets import QApplication
from core_utils import setup_logging, register_nvidia_dlls
from ui_launcher import LauncherWindow

if __name__ == "__main__":
    setup_logging()
    register_nvidia_dlls()
    
    app = QApplication(sys.argv)
    launcher = LauncherWindow()
    launcher.show()
    
    app.exec() # 运行主循环
    
    # 🛑 新增：当主循环结束（窗口都关闭）后，强制杀掉当前进程
    # 这能保证无论有没有僵尸线程，程序都会彻底消失，不留内存垃圾
    os._exit(0)