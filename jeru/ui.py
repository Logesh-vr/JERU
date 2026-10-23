from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QPushButton, QScrollArea, QSpinBox, QTabWidget,
    QTextEdit, QVBoxLayout, QWidget,
)

from .config import Settings

STYLE = """
QWidget { background:#11121a; color:#e8e8f2; font-family:'Segoe UI'; font-size:14px; }
QLabel { background:transparent; }
QMainWindow, QDialog { background:#11121a; }
QPushButton { background:#242632; border:1px solid #393b4b; border-radius:9px; padding:10px 15px; }
QPushButton:hover { background:#303342; border-color:#8270b9; }
QPushButton:pressed { background:#414357; }
QPushButton:disabled { color:#646675; border-color:#2a2c36; }
QPushButton#primary { background:#b6a2ef; color:#181422; border:none; font-weight:600; }
QPushButton#primary:hover { background:#c8b7fa; }
QPushButton#stop { border-color:#705044; color:#efb99d; }
QLineEdit, QTextEdit, QListWidget, QComboBox, QSpinBox, QDoubleSpinBox { background:#1b1d28; border:1px solid #343646; border-radius:8px; padding:9px; selection-background-color:#59467c; }
QTextEdit { padding:13px; }
QListWidget::item { padding:8px; }
QListWidget::item:selected { background:#413453; }
QTabWidget::pane { border:1px solid #343646; border-radius:8px; padding:12px; }
QTabBar::tab { background:#1b1d28; padding:10px 13px; }
QTabBar::tab:selected { background:#383044; color:#cbb9fa; }
QCheckBox { spacing:9px; padding:5px 0; }
QCheckBox::indicator { width:17px; height:17px; }
QScrollArea { border:none; }
QToolTip { background:#292b39; color:#eeeeff; border:1px solid #6b5b90; }
"""


def load_fonts():
    import os
    folder = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    # Offscreen Qt has no Windows font database. Explicitly register installed
    # fonts for reproducible previews; no proprietary font is redistributed.
    for name in ("segoeui.ttf", "segoeuib.ttf", "nirmala.ttc", "Nirmala.ttc", "latha.ttf"):
        path = folder / name
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))


def icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#b6a2ef"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(2, 2, 60, 60, 17, 17)
    painter.setPen(QPen(QColor("#17121f"), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(37, 18, 37, 39)
    painter.drawArc(20, 31, 17, 18, 180 * 16, 180 * 16)
    painter.end()
    return QIcon(pixmap)


class VoiceOrb(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(128, 128)
        self.level, self.phase, self.active = 0.0, 0.0, False
        self.timer = QTimer(self)
        self.timer.setInterval(45)
        self.timer.timeout.connect(self.tick)

    def tick(self):
        self.phase += 0.12
        self.update()

    def set_active(self, active: bool):
        self.active = active
        self.timer.start() if active else self.timer.stop()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(self.width()/144, self.height()/144)
        color = QColor("#b6a2ef" if self.active else "#5b566a")
        p.setPen(QPen(QColor("#252433"), 1))
        p.setBrush(QColor("#1a1824"))
        p.drawEllipse(15, 15, 114, 114)
        radius = 55 + (3 + self.level * 7) * (0.5 + math.sin(self.phase) * 0.5) if self.active else 55
        p.setPen(QPen(color, 1.8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(int(72-radius), int(72-radius), int(radius*2), int(radius*2))
        p.setPen(QPen(color, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawRoundedRect(62, 43, 20, 38, 10, 10)
        p.drawArc(52, 57, 40, 35, 180*16, 180*16)
        p.drawLine(72, 92, 72, 103)
        p.drawLine(61, 103, 83, 103)


class Window(QMainWindow):
    listen = Signal()
    pause = Signal()
    stop = Signal()
    submitted = Signal(str)
    settings_requested = Signal()
    confirmed = Signal()
    choice_selected = Signal(int)
    quit_requested = Signal()
    project_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jeru · Local voice assistant")
        self.setWindowIcon(icon())
        self.setMinimumSize(610, 710)
        self.resize(700, 820)
        self.setStyleSheet(STYLE)
        self.really_quit = False
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(30, 25, 30, 22)
        layout.setSpacing(12)
        header = QHBoxLayout()
        title = QLabel("JERU")
        title.setStyleSheet("font-size:25px; font-weight:650; letter-spacing:5px;")
        header.addWidget(title)
        header.addStretch()
        badge = QLabel("●  LOCAL / OFFLINE")
        badge.setStyleSheet("color:#b9abd6; font-size:11px; letter-spacing:1px;")
        header.addWidget(badge)
        layout.addLayout(header)
        strap = QLabel("Your laptop. Your voice.")
        strap.setStyleSheet("color:#9694a9; font-size:14px;")
        layout.addWidget(strap)
        self.orb = VoiceOrb()
        layout.addWidget(self.orb, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.state = QLabel("Ready when you are")
        self.state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state.setStyleSheet("font-size:25px; font-weight:550;")
        layout.addWidget(self.state)
        self.caption = QLabel("English · தமிழ் · Mixed speech\nClick Listen, or press Ctrl+Alt+J from any app.")
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setStyleSheet("color:#aaa6bd; line-height:1.5;")
        layout.addWidget(self.caption)
        actions = QHBoxLayout()
        self.listen_button = QPushButton("Listen")
        self.listen_button.setObjectName("primary")
        self.listen_button.setToolTip("Listen to one command. Wake listening stays on until Pause.")
        self.listen_button.clicked.connect(self.listen)
        actions.addWidget(self.listen_button, 2)
        self.pause_button = QPushButton("Pause mic")
        self.pause_button.clicked.connect(self.pause)
        actions.addWidget(self.pause_button)
        stop = QPushButton("Stop")
        stop.setObjectName("stop")
        stop.setToolTip("Cancel this task and speech. Ctrl+Alt+K. Completed actions cannot be undone.")
        stop.clicked.connect(self.stop)
        actions.addWidget(stop)
        layout.addLayout(actions)
        self.transcript = QTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setPlaceholderText('Say “Jeru, YouTube open pannu.”\nOr type a command below.\n\nThe microphone starts only when you choose Listen.')
        self.transcript.setMinimumHeight(100)
        self.transcript.document().setMaximumBlockCount(140)
        layout.addWidget(self.transcript, 1)
        self.confirm_box = QFrame()
        self.confirm_box.setStyleSheet("QFrame {background:#2b2424;border-radius:8px;}")
        confirm_layout = QHBoxLayout(self.confirm_box)
        self.confirm_text = QLabel()
        self.confirm_text.setWordWrap(True)
        confirm_layout.addWidget(self.confirm_text, 1)
        confirm = QPushButton("Confirm")
        confirm.clicked.connect(self.confirmed)
        confirm_layout.addWidget(confirm)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.stop)
        confirm_layout.addWidget(cancel)
        self.confirm_box.hide()
        layout.addWidget(self.confirm_box)
        self.choices = QListWidget()
        self.choices.setMaximumHeight(145)
        self.choices.itemClicked.connect(lambda item: self.choice_selected.emit(self.choices.row(item)))
        self.choices.hide()
        layout.addWidget(self.choices)
        entry = QHBoxLayout()
        self.command = QLineEdit()
        self.command.setPlaceholderText("Type an instruction…")
        self.command.setMaxLength(8000)
        self.command.returnPressed.connect(self.submit)
        entry.addWidget(self.command, 1)
        send = QPushButton("Send")
        send.clicked.connect(self.submit)
        entry.addWidget(send)
        layout.addLayout(entry)
        self.model_status = QLabel("Checking local components…")
        self.model_status.setWordWrap(True)
        self.model_status.setStyleSheet("color:#aaa6bd;font-size:12px;")
        layout.addWidget(self.model_status)
        self.light_status = QLabel("Keyboard light turns on while listening, then restores its previous level.")
        self.light_status.setStyleSheet("color:#858198;font-size:11px;")
        self.light_status.setWordWrap(True)
        layout.addWidget(self.light_status)
        footer = QHBoxLayout()
        foot = QLabel("No cloud AI · No API keys")
        foot.setStyleSheet("color:#777387;font-size:11px;")
        footer.addWidget(foot)
        footer.addStretch()
        self.project_button = QPushButton("Open project")
        self.project_button.clicked.connect(self.project_requested)
        self.project_button.hide()
        footer.addWidget(self.project_button)
        settings = QPushButton("Settings")
        settings.clicked.connect(self.settings_requested)
        footer.addWidget(settings)
        layout.addLayout(footer)

    def submit(self):
        text = self.command.text().strip()
        if text:
            self.command.clear()
            self.submitted.emit(text)

    def log(self, label: str, text: str):
        # appendPlainText equivalent prevents source/model text becoming HTML.
        cursor = self.transcript.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        if not self.transcript.document().isEmpty():
            cursor.insertText("\n\n")
        cursor.insertText(f"{label.upper()}\n{text}")
        self.transcript.setTextCursor(cursor)
        self.transcript.ensureCursorVisible()

    def set_state(self, state: str):
        self.state.setText(state)
        self.orb.set_active(state == "Listening")

    def closeEvent(self, event):
        if self.really_quit:
            event.accept()
        else:
            event.ignore()
            self.hide()


class SettingsDialog(QDialog):
    helper_requested = Signal()
    test_light_requested = Signal()

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        import sounddevice as sd
        self.settings = settings
        self.setWindowTitle("Jeru settings")
        self.resize(660, 620)
        self.setStyleSheet(STYLE)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)
        voice = QWidget()
        form = QFormLayout(voice)
        form.setSpacing(15)
        self.language = QComboBox()
        for label, value in (("Automatic · English + Tamil", "auto"), ("English", "en"), ("Tamil / தமிழ்", "ta")):
            self.language.addItem(label, value)
        self.language.setCurrentIndex(max(0, self.language.findData(settings.language)))
        form.addRow("Recognition", self.language)
        self.reply = QComboBox()
        self.reply.addItem("English", "en")
        self.reply.addItem("Tamil / தமிழ் · offline Tamil voice required", "ta")
        self.reply.setCurrentIndex(max(0, self.reply.findData(settings.reply_language)))
        form.addRow("Spoken replies", self.reply)
        self.mic = QComboBox()
        self.mic.addItem("Windows default microphone", None)
        try:
            for i, device in enumerate(sd.query_devices()):
                if device["max_input_channels"]:
                    self.mic.addItem(f'{device["name"]} ({sd.query_hostapis(device["hostapi"])["name"]})', i)
        except Exception:
            pass
        self.mic.setCurrentIndex(max(0, self.mic.findData(settings.microphone)))
        form.addRow("Microphone", self.mic)
        self.speak = QCheckBox("Speak responses · offline female voice")
        self.speak.setToolTip("Installed Windows female English voice; eSpeak female variant for synthetic Tamil speech.")
        self.speak.setChecked(settings.speak)
        form.addRow(self.speak)
        self.startup = QCheckBox("Start Jeru at Windows sign-in")
        self.startup.setChecked(settings.start_with_windows)
        form.addRow(self.startup)
        self.wake = QCheckBox('Listen for “Jeru” while the microphone is enabled')
        self.wake.setChecked(settings.wake_enabled)
        form.addRow(self.wake)
        self.threshold = QDoubleSpinBox()
        self.threshold.setDecimals(3)
        self.threshold.setRange(0.002, 0.15)
        self.threshold.setSingleStep(0.002)
        self.threshold.setValue(settings.speech_threshold)
        form.addRow("Microphone threshold", self.threshold)
        hint = QLabel("Lower this if quiet speech is missed. Raise it if fan noise keeps a command recording.")
        hint.setWordWrap(True)
        form.addRow(hint)
        self.silence = QDoubleSpinBox()
        self.silence.setRange(0.5, 3.0)
        self.silence.setSingleStep(0.1)
        self.silence.setValue(settings.silence_seconds)
        form.addRow("End after silence (seconds)", self.silence)
        tabs.addTab(voice, "Voice")
        files = QWidget()
        files_layout = QFormLayout(files)
        self.models = QLineEdit(settings.model_root)
        self.projects = QLineEdit(settings.projects_root)
        files_layout.addRow("Models", self.path_picker(self.models))
        files_layout.addRow("New projects", self.path_picker(self.projects))
        self.movie_list = QListWidget()
        self.movie_list.addItems(settings.media_folders)
        files_layout.addRow("Movie folders", self.movie_list)
        row = QHBoxLayout()
        add = QPushButton("Add movie folder")
        add.clicked.connect(self.add_movie)
        remove = QPushButton("Remove selected")
        remove.clicked.connect(lambda: self.movie_list.takeItem(self.movie_list.currentRow()))
        row.addWidget(add)
        row.addWidget(remove)
        files_layout.addRow(row)
        hint = QLabel("Models stay on disk. Jeru never downloads a missing model automatically. Movie search scans only the folders selected here.")
        hint.setWordWrap(True)
        files_layout.addRow(hint)
        tabs.addTab(files, "Files")
        aliases = QWidget()
        alias_layout = QVBoxLayout(aliases)
        alias_layout.addWidget(QLabel("Saved names for your folders and apps"))
        self.alias_list = QListWidget()
        for kind, mapping in (("Folder", settings.aliases), ("App", settings.app_aliases)):
            for name, path in mapping.items():
                item = QListWidgetItem(f"{kind}: {name} → {path}")
                item.setData(Qt.ItemDataRole.UserRole, (kind, name, path))
                self.alias_list.addItem(item)
        alias_layout.addWidget(self.alias_list)
        self.alias_name = QLineEdit()
        self.alias_name.setPlaceholderText("Name you will say, e.g. college work")
        alias_layout.addWidget(self.alias_name)
        buttons = QHBoxLayout()
        for label, kind in (("Add folder", "Folder"), ("Add app", "App")):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, k=kind: self.add_alias(k))
            buttons.addWidget(button)
        remove_alias = QPushButton("Remove selected")
        remove_alias.clicked.connect(lambda: self.alias_list.takeItem(self.alias_list.currentRow()))
        buttons.addWidget(remove_alias)
        alias_layout.addLayout(buttons)
        tabs.addTab(aliases, "Aliases")
        lights = QWidget()
        light_form = QFormLayout(lights)
        self.backlight = QCheckBox("Turn keyboard light on while listening")
        self.backlight.setChecked(settings.backlight_enabled)
        light_form.addRow(self.backlight)
        self.brightness = QComboBox()
        self.brightness.addItem("Low", 1)
        self.brightness.addItem("High", 2)
        self.brightness.setCurrentIndex(max(0, self.brightness.findData(settings.backlight_level)))
        light_form.addRow("Listening brightness", self.brightness)
        test = QPushButton("Test light for 2 seconds")
        test.clicked.connect(self.test_light_requested)
        light_form.addRow(test)
        explanation = QLabel("Supported Lenovo white backlights use the existing Lenovo driver. Your previous level is restored after listening, on Pause, and on normal exit. Other keyboards may need a different adapter.")
        explanation.setWordWrap(True)
        light_form.addRow(explanation)
        helper = QPushButton("Enable optional Lenovo light helper…")
        helper.clicked.connect(self.helper_requested)
        light_form.addRow(helper)
        warning = QLabel("Only needed if direct access fails. Windows will ask for administrator consent. The helper controls keyboard brightness only; Jeru stays a normal user app.")
        warning.setWordWrap(True)
        light_form.addRow(warning)
        tabs.addTab(lights, "Keyboard")
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def path_picker(self, line):
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(line)
        button = QPushButton("Browse")
        def browse():
            path = QFileDialog.getExistingDirectory(self, "Choose folder", line.text())
            if path:
                line.setText(path)
        button.clicked.connect(browse)
        row.addWidget(button)
        return container

    def add_movie(self):
        path = QFileDialog.getExistingDirectory(self, "Choose a movie folder")
        if path and not self.movie_list.findItems(path, Qt.MatchFlag.MatchExactly):
            self.movie_list.addItem(path)

    def add_alias(self, kind):
        name = self.alias_name.text().strip().lower()
        if not name:
            self.alias_name.setPlaceholderText("Enter a name before choosing a file")
            return
        path = QFileDialog.getExistingDirectory(self, "Choose folder") if kind == "Folder" else QFileDialog.getOpenFileName(self, "Choose app", "", "Windows application (*.exe *.lnk)")[0]
        if path:
            item = QListWidgetItem(f"{kind}: {name} → {path}")
            item.setData(Qt.ItemDataRole.UserRole, (kind, name, path))
            self.alias_list.addItem(item)
            self.alias_name.clear()

    def apply(self):
        s = self.settings
        s.language, s.reply_language = self.language.currentData(), self.reply.currentData()
        s.microphone, s.speak, s.wake_enabled = self.mic.currentData(), self.speak.isChecked(), self.wake.isChecked()
        s.start_with_windows = self.startup.isChecked()
        s.speech_threshold, s.silence_seconds = self.threshold.value(), self.silence.value()
        s.model_root, s.projects_root = self.models.text().strip(), self.projects.text().strip()
        s.media_folders = [self.movie_list.item(i).text() for i in range(self.movie_list.count())]
        s.backlight_enabled, s.backlight_level = self.backlight.isChecked(), self.brightness.currentData()
        s.aliases, s.app_aliases = {}, {}
        for i in range(self.alias_list.count()):
            kind, name, path = self.alias_list.item(i).data(Qt.ItemDataRole.UserRole)
            (s.aliases if kind == "Folder" else s.app_aliases)[name] = path
        s.save()
