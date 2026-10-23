import json

from jeru.config import Settings


def test_corrupt_settings_fall_back(tmp_path):
    file = tmp_path / "settings.json"
    file.write_text("{broken", encoding="utf-8")
    assert Settings.load(file).language == "auto"


def test_invalid_numeric_and_path_settings_do_not_crash(tmp_path):
    file = tmp_path / "settings.json"
    file.write_text(json.dumps({"speech_threshold": "bad", "silence_seconds": None, "backlight_level": [], "model_root": 42, "media_folders": [False, "C:/Movies"], "aliases": {"bad": False, "good": "C:/Good"}}))
    settings = Settings.load(file)
    assert settings.speech_threshold == 0.012
    assert settings.backlight_level == 2
    assert isinstance(settings.model_root, str)
    assert settings.media_folders == ["C:/Movies"]
    assert settings.aliases == {"good": "C:/Good"}


def test_roundtrip_preserves_tamil_and_does_not_enable_history(tmp_path):
    file = tmp_path / "settings.json"
    settings = Settings(aliases={"கல்லூரி": "C:/College"})
    settings.save(file)
    assert Settings.load(file).aliases == settings.aliases
    assert not Settings.load(file).keep_history
