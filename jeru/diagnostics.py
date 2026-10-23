"""A reproducible packaged-runtime check; never records the microphone."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import wave
from pathlib import Path


def run(output: Path):
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["JERU_DATA_DIR"] = str(output.parent / "diagnostic-data")
    os.environ["JERU_OFFLINE_AUDIT"] = "1"
    attempts = []
    def deny(*args, **kwargs):
        attempts.append("Python network connection attempted")
        raise RuntimeError("Network disabled for the packaged runtime check")
    socket.socket.connect = deny
    socket.create_connection = deny
    report = {"microphone_recorded": False}
    try:
        from .config import Settings, app_root, offline_environment
        from . import __version__
        offline_environment()
        from PySide6.QtWidgets import QApplication
        from .ui import Window, load_fonts
        app = QApplication([])
        load_fonts()
        window = Window()
        window.show()
        app.processEvents()
        screenshot = output.with_suffix(".png")
        window.grab().save(str(screenshot))
        report.update({"version": __version__, "native_ui": True, "screenshot": str(screenshot)})
        import sounddevice as sd
        report["input_devices"] = sum(1 for d in sd.query_devices() if d["max_input_channels"])
        import pythoncom
        import win32com.client
        from .speech import Speaker, TAMIL_VOICE, select_female_english_voice
        pythoncom.CoInitialize()
        try:
            sapi = win32com.client.Dispatch("SAPI.SpVoice")
            report["english_voices"] = sapi.GetVoices().Count
            report["english_voice"] = select_female_english_voice(sapi)
            stream = win32com.client.Dispatch("SAPI.SpFileStream")
            english_wav = output.with_name(output.stem + "-english.wav")
            stream.Open(str(english_wav), 3)
            try:
                sapi.AudioOutputStream = stream
                sapi.Speak("Hello, I am Jeru. I opened YouTube in your default browser.")
            finally:
                stream.Close()
            with wave.open(str(english_wav)) as audio:
                report["female_english_audio_seconds"] = round(audio.getnframes() / audio.getframerate(), 2)
        finally:
            pythoncom.CoUninitialize()
        settings = Settings.load()
        settings.model_root = str(app_root() / "models")
        report["models"] = {name: json.loads((settings.models / name / "jeru-manifest.json").read_text(encoding="utf-8"))["source"] for name in ("speech", "wake", "brain")}
        report["tamil_voice"] = bool(Speaker.espeak())
        exe = Speaker.espeak()
        if exe:
            tamil_wav = output.with_name(output.stem + "-tamil.wav")
            subprocess.run([str(exe), "--path=" + str(exe.parent), "-v", TAMIL_VOICE, "-s", "145", "-w", str(tamil_wav), "--stdin"], input="வணக்கம். இணைப்பை உங்கள் உலாவிக்கு அனுப்பிவிட்டேன்.".encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            report["tamil_voice_variant"] = TAMIL_VOICE
            with wave.open(str(tamil_wav)) as audio:
                report["female_tamil_audio_seconds"] = round(audio.getnframes() / audio.getframerate(), 2)
        from .intents import parse
        phrases = ["YouTube open பண்ணா", "யூடியூப் ஓபன் பண்ணா", "யூட்யூப் ஓப்பன் பண்ணுங்க", "ஜெரு யூ டியூப் ஓபன் பண்ணு"]
        report["mixed_youtube_routing"] = all(parse(t).kind == "open_url" and parse(t).args.get("url") == "https://www.youtube.com" for t in phrases)
        from .voice import VoiceEngine, VoiceEvents
        voice = object.__new__(VoiceEngine)
        voice.settings = settings
        voice._model_root = voice._recognizer = voice._spotter = None
        voice.events = VoiceEvents()
        voice._load()
        report["speech_loaded"] = True
        report["wake_loaded"] = voice._spotter is not None
        from .ai import LocalBrain
        t = time.monotonic()
        action = LocalBrain(settings).interpret("Please open YouTube for me")
        report["local_action"] = {"kind": action.kind, "args": action.args}
        report["local_action_seconds"] = round(time.monotonic()-t, 3)
        report["passed"] = action.kind == "open_url" and action.args.get("url") == "https://www.youtube.com" and report["wake_loaded"] and report["mixed_youtube_routing"] and report.get("female_english_audio_seconds", 0) > 0 and report.get("female_tamil_audio_seconds", 0) > 0
        window.really_quit = True
        window.close()
    except Exception as exc:
        report.update({"passed": False, "error": f"{type(exc).__name__}: {str(exc)[:600]}"})
    finally:
        report["python_network_attempts"] = attempts
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report.get("passed") else 1
