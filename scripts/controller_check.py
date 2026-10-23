"""Exercise native UI → controller → local database and the listening light."""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["JERU_DATA_DIR"] = str(ROOT / "artifacts/controller-data")
os.environ["JERU_TEST_MODE"] = "1"
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pythoncom
from PySide6.QtWidgets import QApplication
import jeru.app as module
from jeru.config import Settings
from jeru.lighting import LenovoLighting
from jeru.ui import Window, load_fonts

app = QApplication([])
load_fonts()
window = Window()
settings = Settings.load()
settings.speak = False
settings.model_root = str(ROOT / "models")
module.session_unlocked = lambda: True
controller = module.Controller(app, window, settings)
statuses = []
controller.events.light_status.connect(statuses.append)


def wait_for(predicate, seconds=5):
    limit = time.monotonic()+seconds
    while time.monotonic() < limit:
        app.processEvents()
        if predicate():
            return
        time.sleep(.02)
    raise TimeoutError("Controller check did not complete")


report = {}
pythoncom.CoInitialize()
light = LenovoLighting()
original = None
try:
    controller.submit("note controller flow verified")
    wait_for(lambda: not controller.busy)
    assert (controller.executor.root / "notes.sqlite3").is_file()
    report["ui_to_local_notes"] = True
    controller.submit("shutdown laptop")
    assert controller.pending is not None and not controller.busy
    controller.cancel()
    assert controller.pending is None
    report["shutdown_requires_confirmation_and_cancels"] = True
    original = light.connect()
    controller.voice_state("Listening")
    wait_for(lambda: any("on · listening" in s for s in statuses))
    during = light.get()
    controller.voice_state("Transcribing")
    wait_for(lambda: any("restored" in s.lower() for s in statuses))
    after = light.get()
    assert during == 2 and after == original
    report["listening_backlight"] = {"before": original, "listening": during, "after": after, "passed": True}
    report["microphone_recorded"] = False
    report["passed"] = True
finally:
    if original is not None:
        light.set(original)
    light.close()
    pythoncom.CoUninitialize()
    controller.cleanup()
    window.really_quit = True
    window.close()
out = ROOT / "artifacts/controller-check.json"
out.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
