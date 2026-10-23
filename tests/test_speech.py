from types import SimpleNamespace

import pytest

from jeru.speech import select_female_english_voice


def voice(name, gender, language):
    return SimpleNamespace(Id=name, GetDescription=lambda: name,
                           GetAttribute=lambda key: {"Gender": gender, "Language": language}[key])


def test_male_system_default_does_not_override_female_english_selection():
    male = voice("David", "Male", "409")
    tamil = voice("Tamil female", "Female", "449")
    female = voice("Zira", "Female", "409")
    sapi = SimpleNamespace(Voice=male, GetVoices=lambda: [male, tamil, female])
    result = select_female_english_voice(sapi)
    assert sapi.Voice is female
    assert result["name"] == "Zira"
    assert result["gender"] == "Female"


def test_missing_female_voice_does_not_silently_use_male_default():
    male = voice("David", "Male", "409")
    sapi = SimpleNamespace(Voice=male, GetVoices=lambda: [male])
    with pytest.raises(ValueError, match="No offline female English voice"):
        select_female_english_voice(sapi)
