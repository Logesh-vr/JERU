import pytest

from jeru.lighting import Indicator


class Light:
    def __init__(self, level):
        self.level = level
        self.changes = []
        self.fail_once = False

    def get(self):
        return self.level

    def set(self, level):
        if self.fail_once:
            self.fail_once = False
            raise OSError("Driver disconnected")
        self.level = level
        self.changes.append(level)


@pytest.mark.parametrize("original", [0, 1, 2])
def test_listening_restores_original_level(original):
    light = Light(original)
    indicator = Indicator(light)
    indicator.listening(True, 2)
    indicator.listening(True, 2)
    assert light.level == 2
    indicator.listening(False)
    assert light.level == original
    assert indicator.previous is None


def test_failed_activation_restores_level():
    light = Light(1)
    indicator = Indicator(light)
    light.fail_once = True
    with pytest.raises(OSError):
        indicator.listening(True, 2)
    assert light.level == 1
    assert indicator.previous is None


def test_failed_restore_can_be_retried():
    light = Light(0)
    indicator = Indicator(light)
    indicator.listening(True, 2)
    light.fail_once = True
    with pytest.raises(OSError):
        indicator.restore()
    assert indicator.previous == 0
    indicator.restore()
    assert light.level == 0
