import threading
from types import SimpleNamespace

from jeru.app import Controller


def test_sign_in_starts_wake_detection_without_recording_a_command():
    voice = SimpleNamespace(**{name: threading.Event() for name in ["manual", "enabled", "cancelled", "suspended"]})
    voice.cancelled.set()
    tips = []
    controller = SimpleNamespace(voice=voice, busy=False, tray=SimpleNamespace(setToolTip=tips.append))
    Controller.start_wake(controller)
    assert voice.enabled.is_set()
    assert not voice.manual.is_set()
    assert not voice.cancelled.is_set()
    assert tips
