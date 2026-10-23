from pathlib import Path

import pytest

from jeru.actions import Executor
from jeru.config import Settings
from jeru.intents import Action


@pytest.fixture
def executor(tmp_path):
    return Executor(Settings(projects_root=str(tmp_path / "projects")), tmp_path / "data")


@pytest.mark.parametrize("url", ["file:///C:/Windows/System32/cmd.exe", "javascript:alert(1)", "ms-settings:", "https://name:password@example.com", "https://example.com\nother"])
def test_only_ordinary_web_urls_are_launched(executor, url, monkeypatch):
    monkeypatch.setattr("os.startfile", lambda *args: pytest.fail("Must not launch"))
    with pytest.raises(ValueError):
        executor.execute(Action("open_url", {"url": url}))


@pytest.mark.parametrize("seconds", [0, -5, 86401, True, "60"])
def test_timer_argument_bounds(executor, seconds):
    with pytest.raises(ValueError):
        executor.execute(Action("timer", {"seconds": seconds}))


def test_alias_cannot_substitute_another_path(executor):
    executor.settings.aliases = {"school": "C:/School"}
    with pytest.raises(ValueError):
        executor.execute(Action("open_alias", {"name": "school", "path": "C:/Private"}))


def test_media_cannot_escape_selected_folders(executor, tmp_path):
    executor.settings.media_folders = [str(tmp_path / "movies")]
    with pytest.raises(ValueError):
        executor.execute(Action("open_media", {"path": str(tmp_path / "other/movie.mp4")}))


def test_media_search_requires_disambiguation(executor, tmp_path, monkeypatch):
    movies = tmp_path / "movies"
    movies.mkdir()
    (movies / "Interstellar-1080p.mkv").touch()
    (movies / "Interstellar-4k.mp4").touch()
    executor.settings.media_folders = [str(movies)]
    monkeypatch.setattr("os.startfile", lambda *args: pytest.fail("Must ask which file"))
    result = executor.execute(Action("find_media", {"query": "interstellar"}))
    assert len(result.choices) == 2


def test_notes_are_stored_locally(executor):
    result = executor.execute(Action("note", {"text": "தமிழ் and English"}))
    assert "Saved" in result.message
    assert (executor.root / "notes.sqlite3").is_file()
