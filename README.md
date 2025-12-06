# woof

基于 OpenAI Whisper 的 Windows 本地实时字幕工具。
**纯源码运行版本，无需下载巨大的 EXE 文件。**

## ✨ 功能
* 系统内录（无需麦克风）
* GPU 实时加速 (CUDA)
* 自动繁简转换
* 实时日志导出

## 🛠️ 如何运行 (Usage)

### 1. 准备环境
确保你的电脑安装了：
* **Python 3.10+**
* **Git**
* **NVIDIA 显卡驱动** (CUDA 12.x 或 13.x)

### 2. 下载代码
```bash
git clone [https://github.com/你的用户名/仓库名.git](https://github.com/你的用户名/仓库名.git)
cd 仓库名
3. 安装依赖 (关键)
Bash

pip install -r requirements.txt
4. 启动
Bash

python main.py
⚠️ 常见报错
如果提示 cublas64_12.dll not found，请确保 pip 安装过程没有报错，且显卡驱动正常。