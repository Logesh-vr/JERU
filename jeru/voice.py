from __future__ import annotations

import queue
import threading
import time
from collections import deque

import numpy as np
from PySide6.QtCore import QObject, Signal

from .config import Settings, offline_environment

RATE = 16000
BLOCK = 800


class VoiceEvents(QObject):
    state = Signal(str)
    transcript = Signal(str)
    level = Signal(float)
    error = Signal(str)
    status = Signal(str)
    activated = Signal()


class VoiceEngine(threading.Thread):
    def __init__(self, settings: Settings, speaker_busy: threading.Event):
        super().__init__(daemon=True, name="jeru-voice")
        self.settings = settings
        self.events = VoiceEvents()
        self.speaker_busy = speaker_busy
        self.enabled = threading.Event()
        self.manual = threading.Event()
        self.cancelled = threading.Event()
        self.suspended = threading.Event()
        self.finished = threading.Event()
        self._recognizer = None
        self._spotter = None
        self._model_root = None
        self.start()

    def activate(self):
        self.cancelled.clear()
        self.manual.set()
        self.enabled.set()

    def pause(self):
        self.enabled.clear()
        self.manual.clear()
        self.cancelled.set()

    def cancel_turn(self):
        self.cancelled.set()
        self.manual.clear()

    def stop(self):
        self.finished.set()
        self.pause()

    def _load(self):
        offline_environment()
        root = self.settings.models
        if self._model_root != str(root):
            self._recognizer = self._spotter = None
            self._model_root = str(root)
        if self._recognizer is None:
            if not (root / "speech/model.bin").is_file():
                raise ValueError("Speech model missing. Choose a provisioned model folder in Settings.")
            self.events.state.emit("Loading speech model")
            from faster_whisper import WhisperModel
            self._recognizer = WhisperModel(str(root / "speech"), device="cpu", compute_type="int8", cpu_threads=4, num_workers=1, local_files_only=True)
        if self._spotter is None and (root / "wake/keywords.txt").is_file():
            import sherpa_onnx
            wake = root / "wake"
            def one(prefix):
                paths = sorted(wake.glob(prefix + "*.int8.onnx")) or sorted(wake.glob(prefix + "*.onnx"))
                if not paths:
                    raise ValueError(f"Wake model is missing its {prefix} component")
                return str(paths[0])
            self._spotter = sherpa_onnx.KeywordSpotter(tokens=str(wake / "tokens.txt"), encoder=one("encoder"), decoder=one("decoder"), joiner=one("joiner"), num_threads=1, sample_rate=RATE, feature_dim=80, keywords_file=str(wake / "keywords.txt"), keywords_score=3.0, keywords_threshold=0.2, provider="cpu")
        self.events.status.emit("Local speech ready · English + Tamil")

    def transcribe(self, audio: np.ndarray) -> str:
        self._load()
        language = None if self.settings.language == "auto" else self.settings.language
        def decode(chosen, vad):
            return self._recognizer.transcribe(audio.astype(np.float32), language=chosen, beam_size=3, temperature=0, condition_on_previous_text=False, vad_filter=vad, vad_parameters={"min_silence_duration_ms": 350})
        segments, info = decode(language, True)
        # This assistant is configured for English and Tamil. Very short Tamil
        # commands can be classified as unrelated languages by Whisper.
        if language is None and info.language not in {"en", "ta"}:
            language = "ta"
            segments, info = decode(language, True)
        text = " ".join(segment.text.strip() for segment in segments if segment.no_speech_prob < 0.8).strip()
        if not text and float(np.max(np.abs(audio), initial=0)) > self.settings.speech_threshold:
            # The capture loop already required audible speech. VAD sometimes
            # rejects short commands; retry once without its segment filter.
            segments, _ = decode(language or info.language, False)
            text = " ".join(segment.text.strip() for segment in segments if segment.no_speech_prob < 0.8).strip()
        return text

    def run(self):
        import sounddevice as sd
        while not self.finished.is_set():
            if not self.enabled.wait(0.15):
                continue
            try:
                self._load()
                frames = queue.Queue(maxsize=100)
                def callback(indata, count, timing, status):
                    if self.suspended.is_set() or self.speaker_busy.is_set():
                        return
                    try:
                        frames.put_nowait(indata[:, 0].copy())
                    except queue.Full:
                        pass
                sample_rate = RATE
                try:
                    sd.check_input_settings(device=self.settings.microphone, channels=1, samplerate=RATE)
                except sd.PortAudioError:
                    sample_rate = int(sd.query_devices(self.settings.microphone, "input")["default_samplerate"])
                original_callback = callback
                def resampled(indata, count, timing, status):
                    if sample_rate == RATE:
                        original_callback(indata, count, timing, status)
                    else:
                        samples = np.interp(np.arange(round(count*RATE/sample_rate))*sample_rate/RATE, np.arange(count), indata[:, 0]).astype(np.float32)
                        original_callback(samples[:, None], len(samples), timing, status)
                with sd.InputStream(device=self.settings.microphone, samplerate=sample_rate, channels=1, dtype="float32", blocksize=round(sample_rate*0.05), callback=resampled):
                    self._capture(frames)
            except Exception as exc:
                self.enabled.clear()
                self.events.error.emit(str(exc))
            finally:
                self.events.level.emit(0.0)
                self.events.state.emit("Paused")

    def _capture(self, frames):
        from .actions import session_unlocked
        from .intents import normalize
        spot_stream = self._spotter.create_stream() if self._spotter else None
        pre_roll = deque(maxlen=12)
        recording, recorded = False, []
        started, last_speech, heard_speech = 0.0, 0.0, False
        wake_only_retries = 0
        last_lock_check, unlocked = 0.0, True
        self.cancelled.clear()
        self.events.state.emit("Waiting for Jeru" if self._spotter and self.settings.wake_enabled else "Ready · use Listen or Ctrl+Alt+J")
        while self.enabled.is_set() and not self.finished.is_set():
            now = time.monotonic()
            if now - last_lock_check > 1:
                unlocked = session_unlocked()
                last_lock_check = now
            if not unlocked or self.suspended.is_set() or self.speaker_busy.is_set():
                if recording:
                    recording, recorded = False, []
                    self.events.state.emit("Paused" if not unlocked else "Working")
                while True:
                    try:
                        frames.get_nowait()
                    except queue.Empty:
                        break
                pre_roll.clear()
                self.finished.wait(0.05)
                continue
            try:
                audio = frames.get(timeout=0.15)
            except queue.Empty:
                continue
            rms = float(np.sqrt(np.mean(audio * audio)))
            self.events.level.emit(min(1.0, rms * 15))
            if self.cancelled.is_set():
                self.cancelled.clear()
                recording, recorded, heard_speech = False, [], False
                pre_roll.clear()
                if self._spotter:
                    spot_stream = self._spotter.create_stream()
                self.events.state.emit("Waiting for Jeru" if self._spotter and self.settings.wake_enabled else "Ready · use Listen")
                continue
            pre_roll.append(audio)
            triggered = self.manual.is_set()
            if not recording and not triggered and self.settings.wake_enabled and self._spotter:
                spot_stream.accept_waveform(RATE, audio)
                while self._spotter.is_ready(spot_stream):
                    self._spotter.decode_stream(spot_stream)
                if self._spotter.get_result(spot_stream):
                    triggered = True
                    spot_stream = self._spotter.create_stream()
            if not recording and triggered:
                from_wake = not self.manual.is_set()
                self.manual.clear()
                recording, recorded = True, list(pre_roll) if from_wake else []
                started = last_speech = now
                heard_speech = False
                wake_only_retries = 0
                self.events.activated.emit()
                self.events.state.emit("Listening")
                # A short local tone does not invoke a speech engine or model.
                import winsound
                winsound.Beep(880, 65)
                continue
            if not recording:
                continue
            recorded.append(audio)
            if rms >= self.settings.speech_threshold:
                heard_speech, last_speech = True, now
            duration = now - started
            done = heard_speech and now - last_speech >= self.settings.silence_seconds and duration >= 0.65
            timeout = duration > self.settings.max_record_seconds or not heard_speech and duration > 7
            if done or timeout:
                recording = False
                self.events.state.emit("Transcribing")
                if heard_speech:
                    text = self.transcribe(np.concatenate(recorded))
                    if text and not normalize(text) and wake_only_retries < 1 and not self.cancelled.is_set():
                        # Saying just the name is activation, not the command.
                        # Retain frames queued during STT so an instruction
                        # spoken after the chime is not discarded.
                        wake_only_retries += 1
                        recording, recorded, heard_speech = True, [], False
                        started = last_speech = time.monotonic()
                        pre_roll.clear()
                        self.events.state.emit("Listening")
                        continue
                    if not self.cancelled.is_set() and self.enabled.is_set() and unlocked and normalize(text):
                        # Suspend before emitting, so a following wake cannot race execution.
                        self.suspended.set()
                        self.events.transcript.emit(text)
                    else:
                        self.events.state.emit("Waiting for Jeru")
                else:
                    self.events.status.emit("No speech detected. Try again, or lower the microphone threshold in Settings.")
                    self.events.state.emit("Waiting for Jeru")
                recorded, heard_speech = [], False
                pre_roll.clear()
                while True:
                    try:
                        frames.get_nowait()
                    except queue.Empty:
                        break
                if self._spotter:
                    spot_stream = self._spotter.create_stream()
