from types import SimpleNamespace

import numpy as np

from jeru.config import Settings
from jeru.voice import VoiceEngine


class Recognizer:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def transcribe(self, audio, **kwargs):
        self.calls.append(kwargs)
        language, text = next(self.responses)
        segments = iter([SimpleNamespace(text=text, no_speech_prob=0.1)]) if text else iter([])
        return segments, SimpleNamespace(language=language)


def engine(responses):
    voice = object.__new__(VoiceEngine)
    voice.settings = Settings()
    voice._load = lambda: None
    voice._recognizer = Recognizer(responses)
    return voice


def test_short_command_language_stays_within_configured_languages():
    voice = engine([("de", "unrelated"), ("ta", "யூடியூப் திற")])
    assert voice.transcribe(np.ones(1600, dtype=np.float32)*0.02) == "யூடியூப் திற"
    assert voice._recognizer.calls[-1]["language"] == "ta"


def test_vad_rejection_can_retry_audible_short_command():
    voice = engine([("en", ""), ("en", "Open YouTube")])
    assert voice.transcribe(np.ones(1600, dtype=np.float32)*0.02) == "Open YouTube"
    assert voice._recognizer.calls[-1]["vad_filter"] is False


def test_silence_does_not_retry_into_hallucinated_command():
    voice = engine([("en", "")])
    assert voice.transcribe(np.zeros(1600, dtype=np.float32)) == ""
    assert len(voice._recognizer.calls) == 1
