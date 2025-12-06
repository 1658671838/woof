# woof
# 🎙️ Whisper Real-time Subtitle (本地实时字幕工具)

这是一个基于 OpenAI Whisper 模型的 Windows 本地实时字幕工具。它可以捕获系统内部声音（如浏览器、视频播放器、会议软件），利用 GPU 进行极速转录，并以**透明悬浮窗**的形式实时显示中文字幕。

**完全免费、完全离线、数据安全、支持导出。**

## ✨ 核心功能 (Features)

* **🖥️ 系统内录**：直接监听声卡（Loopback），无需麦克风，不会录入环境杂音。
* **🚀 GPU 加速**：基于 `faster-whisper` 和 CUDA，在 NVIDIA 显卡上实现毫秒级响应。
* **🎨 现代化 GUI**：
    * **启动器**：可视化配置模型大小、下载路径、保存路径。
    * **悬浮窗**：背景透明、鼠标穿透（可选）、支持拖拽、永远置顶。
* **🇨🇳 自动优化**：内置繁体转简体功能，符合中文阅读习惯。
* **📝 实时导出**：支持将识别到的字幕实时保存为 `.txt` 文件，方便后期复盘。
* **💾 配置记忆**：自动保存上一次的设置，下次打开即用。

---

## 📥 下载与使用 (对于普通用户)

不需要安装 Python，直接下载打包好的软件即可使用。

1.  点击右侧的 **[Releases](https://github.com/你的用户名/仓库名/releases)** 页面。
2.  下载最新版本的压缩包（例如 `WhisperSubtitle_v1.0.zip`）。
3.  解压后，双击 **`WhisperSubtitle.exe`** 运行。
4.  在启动器中选择模型大小（推荐 `medium`），点击“启动”。
5.  打开 B站/爱奇艺/YouTube 播放视频，字幕将自动浮现。

> **注意**：本软件需要您的电脑拥有 **NVIDIA 显卡** 并安装了显卡驱动。

---

## 🛠️ 开发与构建 (对于开发者)

如果你想修改源码或自己编译，请按照以下步骤操作。

### 1. 环境要求
* Python 3.8+
* Windows 10/11
* CUDA 12.x 或 13.x 环境

### 2. 安装依赖
```bash
# 建议创建虚拟环境
conda create -n subtitle python=3.10
conda activate subtitle

# 安装项目依赖
pip install -r requirements.txt
3. 运行源码
Bash

python main.py
4. 打包为 EXE
如果你修改了代码并想重新打包：

Bash

pyinstaller --noconfirm --onedir --windowed --name "WhisperSubtitle" --hidden-import=faster_whisper --hidden-import=zhconv --collect-all faster_whisper main.py
打包完成后，程序位于 dist/WhisperSubtitle 文件夹内。

📂 项目结构
Plaintext

/
├── main.py              # 程序主入口 (包含 GUI、线程逻辑、配置管理)
├── requirements.txt     # 依赖清单
├── .gitignore           # Git 忽略配置
└── README.md            # 项目说明文档
⚠️ 常见问题
Q: 第一次启动很慢？

A: 首次运行需要下载 AI 模型（约 500MB - 1.5GB），请耐心等待，启动器上方会有提示。

Q: 报错 cublas64_12.dll not found？

A: 程序内置了自动修复补丁，通常能自动解决。如果仍报错，请检查是否正确安装了 CUDA 驱动。