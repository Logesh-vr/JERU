"""Synthetic audio/model checks. Does not open or record a microphone."""
from __future__ import annotations

import json
import os
import socket
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["JERU_DATA_DIR"] = str(ROOT / ".jeru-data")


def main():
    import numpy as np
    import pythoncom
    import win32com.client
    from jeru.config import Settings, offline_environment
    offline_environment()
    out = ROOT / "artifacts/audio-check"
    out.mkdir(parents=True, exist_ok=True)
    pythoncom.CoInitialize()
    voice = win32com.client.Dispatch("SAPI.SpVoice")
    samples = []
    for text in ("Jeru", "Hey Jeru", "Open YouTube", "Open downloads", "Volume down"):
        filename = out / (text.lower().replace(" ", "-") + ".wav")
        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        stream.Open(str(filename), 3)
        voice.AudioOutputStream = stream
        voice.Speak(text)
        stream.Close()
        with wave.open(str(filename), "rb") as f:
            rate, channels, width = f.getframerate(), f.getnchannels(), f.getsampwidth()
            if width != 2:
                raise ValueError("Synthetic WAV must contain 16-bit PCM")
            audio = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32)/32768
            if channels > 1:
                audio = audio.reshape(-1, channels).mean(axis=1)
            audio = np.interp(np.arange(round(len(audio)*16000/rate))*rate/16000, np.arange(len(audio)), audio).astype(np.float32)
        samples.append((text, audio))
    pythoncom.CoUninitialize()
    attempts = []
    original_connect = socket.socket.connect
    original_create = socket.create_connection
    def deny(*args, **kwargs):
        attempts.append(str(args[1:] if len(args)>1 else args))
        raise RuntimeError("Network is blocked during this offline verification")
    socket.socket.connect = deny
    socket.create_connection = deny
    try:
        from jeru.voice import VoiceEngine
        import threading
        # Build a non-running engine for deterministic file-based inference.
        engine = object.__new__(VoiceEngine)
        engine.settings = Settings.load()
        engine.settings.model_root = str(ROOT / "models")
        engine._recognizer = engine._spotter = None
        engine._model_root = None
        from jeru.voice import VoiceEvents
        engine.events = VoiceEvents()
        engine._load()
        results = []
        for text, audio in samples:
            t = time.monotonic()
            transcript = engine.transcribe(audio)
            spotter = engine._spotter
            detected = []
            if spotter:
                stream = spotter.create_stream()
                padded = np.concatenate([audio, np.zeros(16000, dtype=np.float32)])
                for offset in range(0, len(padded), 1600):
                    stream.accept_waveform(16000, padded[offset:offset+1600])
                    while spotter.is_ready(stream):
                        spotter.decode_stream(stream)
                    result = spotter.get_result(stream)
                    if result:
                        detected.append(result)
                        stream = spotter.create_stream()
            results.append({"source_text": text, "transcript": transcript, "wake_results": detected, "seconds": round(time.monotonic()-t, 3)})
        report = {"scope": "Synthetic Windows voice audio only. Physical microphone, accent, distance, and noise remain unverified.", "network_attempts": attempts, "results": results}
        (out / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        socket.socket.connect = original_connect
        socket.create_connection = original_create


if __name__ == "__main__":
    main()
