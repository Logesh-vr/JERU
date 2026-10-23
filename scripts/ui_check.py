"""Render and exercise Jeru's own native widgets without recording audio."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["JERU_DATA_DIR"] = str(ROOT / ".jeru-data")

from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from jeru.config import Settings
from jeru.ui import SettingsDialog, Window, load_fonts

app = QApplication([])
load_fonts()
window = Window()
window.show()
app.processEvents()
window.log("You", "Jeru, YouTube open pannu")
window.log("Jeru", "Opened the link in your default browser: www.youtube.com. Page loading has not been checked.")
window.set_state("Waiting for Jeru")
out = ROOT / "artifacts/ui"
out.mkdir(parents=True, exist_ok=True)
app.processEvents()
window.grab().save(str(out / "jeru-main.png"))
window.set_state("Listening")
window.orb.level = 0.6
QTest.qWait(100)
window.grab().save(str(out / "jeru-listening.png"))
settings = Settings.load()
dialog = SettingsDialog(settings, window)
dialog.show()
app.processEvents()
dialog.grab().save(str(out / "jeru-settings.png"))
captured = []
window.submitted.connect(captured.append)
window.command.setText("சத்தம் குறை")
window.submit()
assert captured == ["சத்தம் குறை"]
assert window.command.text() == ""
dialog.reject()
window.really_quit = True
window.close()
print(json.dumps({"native_widgets": "pass", "tamil_command_submission": "pass", "microphone_recorded": False, "screenshots": [str(p) for p in out.glob("*.png")]}))
