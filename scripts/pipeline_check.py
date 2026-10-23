"""Synthetic wake → capture → real STT → controller → dispatch check.

Replaces only the microphone stream and final OS action with test doubles.
No microphone is recorded and no browser is opened.
"""
import json
import os
import sys
import threading
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["JERU_DATA_DIR"] = str(ROOT / "artifacts/pipeline-data")
os.environ["JERU_TEST_MODE"] = "1"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import numpy as np
import sounddevice as sd
import winsound
from PySide6.QtWidgets import QApplication
from jeru.app import Controller
from jeru.actions import Result
from jeru.config import Settings
from jeru.ui import Window, load_fonts


def audio(name):
    with wave.open(str(ROOT / "artifacts/audio-check" / name), "rb") as f:
        rate = f.getframerate()
        data = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32)/32768
    return np.interp(np.arange(round(len(data)*16000/rate))*rate/16000, np.arange(len(data)), data).astype(np.float32)


gap = 40000 if "--delayed" in sys.argv else 16000
recording = np.concatenate([np.zeros(3200, np.float32), audio("jeru.wav"), np.zeros(gap, np.float32), audio("open-youtube.wav"), np.zeros(48000, np.float32)])
stream_info = {}


class SyntheticStream:
    def __init__(self, callback, samplerate=16000, blocksize=800, **kwargs):
        self.callback = callback
        self.blocksize = blocksize
        stream_info.update({"samplerate": samplerate, "blocksize": blocksize, "frames": 0})
        self.audio = np.interp(np.arange(round(len(recording)*samplerate/16000))*16000/samplerate, np.arange(len(recording)), recording).astype(np.float32)
        self.stop = threading.Event()

    def __enter__(self):
        def feed():
            for start in range(0, len(self.audio), self.blocksize):
                if self.stop.wait(.05):
                    break
                frame = self.audio[start:start+self.blocksize]
                self.callback(frame[:, None], len(frame), None, None)
                stream_info["frames"] += 1
        self.thread = threading.Thread(target=feed, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(1)


sd.InputStream = SyntheticStream
winsound.Beep = lambda *args: None
app = QApplication([])
load_fonts()
window = Window()
settings = Settings.load()
settings.model_root = str(ROOT / "models")
settings.speak = False
settings.backlight_enabled = False
controller = Controller(app, window, settings)
states, transcripts, actions = [], [], []
levels = []
controller.voice.events.state.connect(states.append)
controller.voice.events.transcript.connect(transcripts.append)
controller.voice.events.level.connect(levels.append)
decode_info = []
original_transcribe = controller.voice.transcribe
def inspect_transcription(samples):
    np.save(ROOT / 'artifacts/pipeline-captured.npy', samples)
    result = original_transcribe(samples)
    decode_info.append({"samples":len(samples),"text":result})
    return result
controller.voice.transcribe = inspect_transcription


def dispatch(action, target=0):
    actions.append({"kind": action.kind, "args": action.args})
    return Result("Synthetic pipeline dispatch verified.")


controller.executor.execute = dispatch
started = time.monotonic()
controller.voice.activate() if "--manual" in sys.argv else controller.voice.enabled.set()
try:
    while time.monotonic()-started < 30:
        app.processEvents()
        if actions and not controller.busy:
            break
        time.sleep(.02)
    passed = bool(actions and actions[0] == {"kind": "open_url", "args": {"url": "https://www.youtube.com"}})
    report = {"passed": passed, "microphone_recorded": False, "real_os_action": False, "real_models": True, "stream": stream_info, "states": states, "level_updates": len(levels), "max_level": max(levels, default=0), "decodes":decode_info, "transcripts": transcripts, "dispatched_actions": actions, "seconds": round(time.monotonic()-started, 2)}
    result_name = "pipeline-delayed-check.json" if "--delayed" in sys.argv else "pipeline-check.json"
    (ROOT / "artifacts" / result_name).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
finally:
    controller.cleanup()
    window.really_quit = True
    window.close()
if not passed:
    raise SystemExit(1)
