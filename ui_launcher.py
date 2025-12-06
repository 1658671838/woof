import os
from PyQt6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QPushButton, QHBoxLayout, 
                             QComboBox, QFileDialog, QCheckBox, QLineEdit, QGroupBox, QMessageBox)
from core_utils import ConfigManager
from ui_overlay import ResizableSubtitleWindow

class LauncherWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Whisper 字幕启动器")
        self.resize(500, 450)
        self.config = ConfigManager.load_config()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        
        # --- 模型设置 ---
        group_model = QGroupBox("🧠 模型设置")
        layout_m = QVBoxLayout()
        
        layout_m.addWidget(QLabel("选择模型大小:"))
        self.combo_size = QComboBox()
        self.combo_size.addItems(["tiny", "base", "small", "medium", "large-v3"])
        self.combo_size.setCurrentText(self.config["model_size"])
        layout_m.addWidget(self.combo_size)

        layout_m.addWidget(QLabel("模型下载/缓存位置:"))
        h_layout_path = QHBoxLayout()
        self.input_model_path = QLineEdit(self.config["model_path"])
        btn_model_path = QPushButton("📂")
        btn_model_path.clicked.connect(lambda: self.select_folder(self.input_model_path))
        h_layout_path.addWidget(self.input_model_path)
        h_layout_path.addWidget(btn_model_path)
        layout_m.addLayout(h_layout_path)
        group_model.setLayout(layout_m)
        layout.addWidget(group_model)

        # --- 外观设置 (新增) ---
        group_ui = QGroupBox("🎨 外观设置")
        layout_u = QVBoxLayout()
        layout_u.addWidget(QLabel("字体大小:"))
        self.combo_font = QComboBox()
        self.combo_font.addItems(["18", "24", "30", "36", "48"])
        self.combo_font.setCurrentText(str(self.config.get("font_size", 24)))
        layout_u.addWidget(self.combo_font)
        group_ui.setLayout(layout_u)
        layout.addWidget(group_ui)

        # --- 导出设置 ---
        group_save = QGroupBox("💾 导出设置")
        layout_s = QVBoxLayout()
        self.check_save = QCheckBox("保存字幕文件")
        self.check_save.setChecked(self.config["save_log"])
        layout_s.addWidget(self.check_save)
        
        layout_s.addWidget(QLabel("保存位置:"))
        h_layout_save = QHBoxLayout()
        self.input_log_path = QLineEdit(self.config["log_path"])
        btn_log_path = QPushButton("📂")
        btn_log_path.clicked.connect(lambda: self.select_folder(self.input_log_path))
        h_layout_save.addWidget(self.input_log_path)
        h_layout_save.addWidget(btn_log_path)
        layout_s.addLayout(h_layout_save)
        group_save.setLayout(layout_s)
        layout.addWidget(group_save)

        # --- 启动 ---
        self.btn_start = QPushButton("🚀 启动字幕")
        self.btn_start.setFixedHeight(50)
        self.btn_start.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.btn_start.clicked.connect(self.start_app)
        layout.addWidget(self.btn_start)

        self.setLayout(layout)

    def select_folder(self, line_edit):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder: line_edit.setText(folder)

    def start_app(self):
        # 保存所有配置
        new_config = {
            "model_size": self.combo_size.currentText(),
            "model_path": self.input_model_path.text() or os.getcwd(),
            "save_log": self.check_save.isChecked(),
            "log_path": self.input_log_path.text(),
            "font_size": int(self.combo_font.currentText()),
            # 保留原有的宽高记忆
            "window_width": self.config.get("window_width", 1000),
            "window_height": self.config.get("window_height", 150)
        }
        ConfigManager.save_config(new_config)
        
        self.hide()
        try:
            self.main_window = ResizableSubtitleWindow(new_config)
            self.main_window.show()
            self.main_window.closed_signal.connect(self.close)
        except Exception as e:
            QMessageBox.critical(self, "启动错误", str(e))
            self.show()