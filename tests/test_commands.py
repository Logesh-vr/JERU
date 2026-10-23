import pytest

from jeru.intents import Action, parse, validate_model_action
from jeru.actions import needs_confirmation


@pytest.mark.parametrize("text,kind,args", [
    ("Jeru, open YouTube", "open_url", {"url": "https://www.youtube.com"}),
    ("YouTube open pannu", "open_url", {"url": "https://www.youtube.com"}),
    ("YouTube open பண்ணா", "open_url", {"url": "https://www.youtube.com"}),
    ("யூடியூப் ஓபன் பண்ணா", "open_url", {"url": "https://www.youtube.com"}),
    ("யூட்யூப் ஓப்பன் பண்ணுங்க", "open_url", {"url": "https://www.youtube.com"}),
    ("ஜெரு, யூ டியூப் ஓபன் பண்ணு.", "open_url", {"url": "https://www.youtube.com"}),
    ("யூடியூப்பை திறக்கவும்", "open_url", {"url": "https://www.youtube.com"}),
    ("YouTube open panna", "open_url", {"url": "https://www.youtube.com"}),
    ("downloads ஓப்பன் பண்ணா", "open_folder", {"name": "Downloads"}),
    ("ஜெரு யூடியூப் திற", "open_url", {"url": "https://www.youtube.com"}),
    ("open downloads folder", "open_folder", {"name": "Downloads"}),
    ("volume konjam kammi pannu", "media", {"key": "volume_down"}),
    ("சத்தம் குறை", "media", {"key": "volume_down"}),
    ("சத்தத்தை கொஞ்சம் குறை", "media", {"key": "volume_down"}),
    ("ஒலியை அதிகப்படுத்து", "media", {"key": "volume_up"}),
    ("pause the movie", "media", {"key": "play_pause"}),
    ("set a timer for 5 minutes", "timer", {"seconds": 300}),
    ("10 seconds timer", "timer", {"seconds": 10}),
    ("note Buy Milk", "note", {"text": "buy milk"}),
    ("note watch YouTube tomorrow", "note", {"text": "watch youtube tomorrow"}),
    ("குறிப்பு நாளை யூடியூப் பார்க்க வேண்டும்", "note", {"text": "நாளை யூடியூப் பார்க்க வேண்டும்"}),
    ("create a Python project called Test Tool", "create_project", {"template": "python", "brief": "test tool"}),
    ("build an expense tracker", "code_project", {"brief": "an expense tracker"}),
    ("stop", "cancel", {}),
    ("restart laptop", "system", {"operation": "restart"}),
])
def test_bilingual_commands(text, kind, args):
    assert parse(text) == Action(kind, args)


def test_alias_only_matches_complete_name():
    aliases = {"college work": "C:/University"}
    assert parse("open my college work folder", aliases).kind == "open_alias"
    assert parse("open my college", aliases).kind == "unknown"
    assert parse("open my college work and delete everything", aliases).kind == "unknown"


def test_search_query_cannot_change_destination():
    action = parse("search youtube for a & redirect=https://evil.example")
    assert action.args["url"].startswith("https://www.youtube.com/results?search_query=")
    assert "%26" in action.args["url"]


@pytest.mark.parametrize("text", ["don't open YouTube", "யூடியூப் திறக்காதே", "YouTube ஓபன் பண்ணாதே", "YouTube open பண்ணாதீங்க", "YouTube tomorrow"])
def test_unrecognized_or_negative_phrase_is_not_treated_as_open(text):
    assert parse(text).kind == "unknown"


def test_youtube_search_is_not_replaced_by_site_open():
    assert parse("search youtube for tamil songs").args["url"] == "https://www.youtube.com/results?search_query=tamil+songs"


def test_model_note_hallucination_is_rejected_before_execution(monkeypatch):
    from jeru.ai import LocalBrain
    from jeru.config import Settings
    brain = LocalBrain(Settings())
    monkeypatch.setattr(brain, "request", lambda *args: {"kind": "note", "args": {"text": "Note: The request is in Tamil. Please provide the request in English."}})
    with pytest.raises(ValueError, match="unsupported action"):
        brain.interpret("யூடியூப் ஓபன் பண்ணா")


@pytest.mark.parametrize("obj", [
    {"kind": "shell", "args": {"command": "Remove-Item C:/"}},
    {"kind": "open_app", "args": {"target": "powershell.exe"}},
    {"kind": "open_alias", "args": {"path": "C:/private"}},
    {"kind": "system", "args": {"operation": "shutdown"}},
    {"kind": "time", "args": {"extra": "value"}},
    {"kind": "timer", "args": {"seconds": True}},
    {"kind": "say", "args": {"text": {"nested": "object"}}},
    {"kind": "open_url", "args": []},
])
def test_model_cannot_expand_its_permissions(obj):
    with pytest.raises(ValueError):
        validate_model_action(obj)


def test_confirmation_boundaries():
    assert needs_confirmation(Action("system", {"operation": "lock"}))
    assert needs_confirmation(Action("window", {"operation": "close"}))
    assert needs_confirmation(Action("dictate", {"text": "private"}))
    assert not needs_confirmation(parse("open youtube"))
