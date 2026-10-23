import os
import subprocess
import sys
from pathlib import Path

from .config import app_root


def set_startup(enabled: bool):
    import win32com.client
    shell = win32com.client.Dispatch("WScript.Shell")
    folder = Path(shell.SpecialFolders("Startup"))
    shortcut_path = folder / "Jeru voice assistant.lnk"
    executable = Path(sys.executable)
    arguments = "--start-listening"
    if not getattr(sys, "frozen", False):
        executable = executable.with_name("pythonw.exe")
        arguments = "-m jeru --start-listening"
    if shortcut_path.exists():
        existing = shell.CreateShortcut(str(shortcut_path))
        if Path(existing.TargetPath).resolve() != executable.resolve() or existing.Description != "Jeru local voice assistant":
            raise ValueError("The Jeru startup shortcut belongs to another installation")
    if enabled:
        shortcut = shell.CreateShortcut(str(shortcut_path))
        shortcut.TargetPath = str(executable)
        shortcut.Arguments = arguments
        shortcut.WorkingDirectory = str(app_root())
        shortcut.Description = "Jeru local voice assistant"
        shortcut.Save()
    elif shortcut_path.exists():
        shortcut_path.unlink()
