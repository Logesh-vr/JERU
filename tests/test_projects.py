import pytest

from jeru.projects import new_project, validate_generated_files, write_generated


@pytest.mark.parametrize("path", ["../escape.py", "/escape.py", "C:/escape.py", "sub/../../escape.py", "sub\\escape.py", ".git/config", "CON.py", "sub/NUL.txt", "escape.py.", "escape.py ", "run.ps1", "run.exe"])
def test_generated_path_boundary(path):
    with pytest.raises(ValueError):
        validate_generated_files({"files": {path: "print('hello')"}})


def test_no_case_collisions_on_windows():
    with pytest.raises(ValueError):
        validate_generated_files({"files": {"main.py": "", "MAIN.py": ""}})


def test_project_creation_does_not_overwrite(tmp_path):
    first = new_project(tmp_path, "expense tracker with charts", "python")
    (first / "main.py").write_text("original", encoding="utf-8")
    second = new_project(tmp_path, "expense tracker with charts", "python")
    assert first != second
    assert (first / "main.py").read_text() == "original"
    assert "expense tracker with charts" in (second / "TASK.md").read_text()


def test_generated_python_is_parsed_without_execution(tmp_path):
    # If executed, this source would create a marker. Only syntax is checked.
    marker = tmp_path / "should-not-exist"
    project = new_project(tmp_path, "safe test", "python")
    issues = write_generated(project, {"main.py": f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"})
    assert not issues
    assert not marker.exists()
    assert (project / "generated-proposal/main.py").exists()


def test_syntax_failure_is_reported(tmp_path):
    project = new_project(tmp_path, "syntax test", "python")
    assert write_generated(project, {"main.py": "def broken(:\n"})
    assert "Static issues" in (project / "GENERATION_REPORT.md").read_text()


def test_filename_echo_is_not_reported_as_implemented_code(tmp_path):
    project = new_project(tmp_path, "filename echo", "python")
    issues = write_generated(project, {"main.py": "main.py"})
    assert any("no executable implementation" in issue for issue in issues)
