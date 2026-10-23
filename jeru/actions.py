from __future__ import annotations

import ctypes
import datetime as dt
import difflib
import json
import os
import shutil
import sqlite3
import subprocess
import winreg
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from .config import Settings, data_root
from .intents import Action, FOLDERS
from .projects import new_project

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MEDIA_KEYS = {"mute": 0xAD, "volume_down": 0xAE, "volume_up": 0xAF, "next": 0xB0, "previous": 0xB1, "play_pause": 0xB3}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".wmv"}


@dataclass
class Result:
    message: str
    choices: list[tuple[str, Action]] = field(default_factory=list)
    project: Path | None = None
    needs_ai: str | None = None
    timer_seconds: int | None = None


def needs_confirmation(action: Action) -> bool:
    return action.kind in {"system", "dictate"} or action.kind == "window" and action.args.get("operation") == "close"


def known_folder(name: str) -> Path:
    reg_names = {"Desktop": "Desktop", "Documents": "Personal", "Videos": "My Video", "Music": "My Music", "Pictures": "My Pictures", "Downloads": "{374DE290-123F-4565-9164-39C4925E467B}"}
    if name not in reg_names:
        raise ValueError("Choose Downloads, Documents, Desktop, Videos, Music, Pictures, or a saved alias")
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
            return Path(os.path.expandvars(winreg.QueryValueEx(key, reg_names[name])[0])).resolve()
    except OSError:
        return Path.home() / name


def foreground_window() -> int:
    ctypes.windll.user32.GetForegroundWindow.restype = ctypes.c_void_p
    return int(ctypes.windll.user32.GetForegroundWindow() or 0)


def session_unlocked() -> bool:
    user = ctypes.windll.user32
    user.OpenInputDesktop.argtypes = [ctypes.c_uint, ctypes.c_bool, ctypes.c_uint]
    user.OpenInputDesktop.restype = ctypes.c_void_p
    user.SwitchDesktop.argtypes = [ctypes.c_void_p]
    user.CloseDesktop.argtypes = [ctypes.c_void_p]
    handle = user.OpenInputDesktop(0, False, 0x100)
    if not handle:
        return False
    try:
        return bool(user.SwitchDesktop(handle))
    finally:
        user.CloseDesktop(handle)


def keypress(key: int, modifier: int | None = None) -> None:
    user = ctypes.windll.user32
    if modifier:
        user.keybd_event(modifier, 0, 0, 0)
    user.keybd_event(key, 0, 0, 0)
    user.keybd_event(key, 0, 2, 0)
    if modifier:
        user.keybd_event(modifier, 0, 2, 0)


class Executor:
    def __init__(self, settings: Settings, root: Path | None = None):
        self.settings = settings
        self.root = root or data_root()
        self.root.mkdir(parents=True, exist_ok=True)

    def execute(self, action: Action, target_window: int = 0) -> Result:
        k, a = action.kind, action.args
        if k == "help":
            return Result("Try: open YouTube; YouTube open pannu; open Downloads; volume down; play movie <title>; note <text>; timer 5 minutes; create a Python project called <name>; or build <your project brief>.")
        if k == "say":
            return Result(str(a["text"])[:1500])
        if k == "time":
            return Result("It's " + dt.datetime.now().strftime("%I:%M %p").lstrip("0") + ".")
        if k == "open_url":
            url = str(a["url"])
            p = urlsplit(url)
            if p.scheme not in {"https", "http"} or not p.hostname or p.username or p.password or any(ord(c) < 32 for c in url):
                raise ValueError("Only ordinary HTTP/HTTPS website links can be opened")
            os.startfile(url)
            return Result(f"Opened the link in your default browser: {p.hostname}. Page loading has not been checked.")
        if k == "open_folder":
            name = str(a["name"])
            name = FOLDERS.get(name.lower(), name)
            if name == "@projects":
                path = Path(self.settings.projects_root).expanduser().resolve()
                path.mkdir(parents=True, exist_ok=True)
            else:
                path = known_folder(name)
            return self.open_path(path)
        if k == "open_alias":
            # The saved mapping is the authority, not a model-supplied path.
            saved = self.settings.aliases.get(a.get("name"))
            if not saved or str(saved) != str(a.get("path")):
                raise ValueError("This folder alias is not registered")
            return self.open_path(Path(saved).expanduser().resolve())
        if k == "open_media":
            path = Path(a["path"]).resolve()
            roots = [Path(p).resolve() for p in self.settings.media_folders]
            if not any(path.is_relative_to(p) for p in roots) or path.suffix.lower() not in VIDEO_EXTENSIONS:
                raise ValueError("Movie is outside the selected movie folders")
            return self.open_path(path)
        if k == "open_app":
            return self.open_app(str(a["target"]), str(a.get("name", "application")))
        if k == "media":
            key = str(a["key"])
            if key not in MEDIA_KEYS:
                raise ValueError("Unsupported media control")
            keypress(MEDIA_KEYS[key])
            return Result("Sent " + key.replace("_", " ") + " to Windows media controls.")
        if k == "window":
            operation = str(a["operation"])
            if operation == "switch":
                keypress(0x09, 0x12)
                return Result("Sent the switch-window command.")
            if not target_window or not ctypes.windll.user32.IsWindow(ctypes.c_void_p(target_window)):
                raise ValueError("No target window was captured. Activate Jeru with the hotkey while your target app is focused.")
            h = ctypes.c_void_p(target_window)
            if operation in {"minimize", "maximize"}:
                ctypes.windll.user32.ShowWindow(h, 6 if operation == "minimize" else 3)
            elif operation == "close":
                ctypes.windll.user32.PostMessageW(h, 0x0010, 0, 0)
            else:
                raise ValueError("Unsupported window operation")
            return Result(f"Sent {operation} to the selected window.")
        if k == "find_media":
            return self.find_media(str(a["query"]))
        if k == "note":
            text = str(a["text"]).strip()
            if not text or len(text) > 8000:
                raise ValueError("Note must contain 1–8000 characters")
            with sqlite3.connect(self.root / "notes.sqlite3") as db:
                db.execute("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, created TEXT NOT NULL, text TEXT NOT NULL)")
                db.execute("INSERT INTO notes(created,text) VALUES (?,?)", (dt.datetime.now().isoformat(timespec="seconds"), text))
            return Result("Saved your note locally.")
        if k == "timer":
            seconds = a["seconds"]
            if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or not 1 <= seconds <= 86400:
                raise ValueError("Timer must be between one second and 24 hours")
            return Result(f"Timer set for {int(seconds)} seconds. Keep Jeru running for the alarm.", timer_seconds=int(seconds))
        if k in {"create_project", "code_project"}:
            brief = str(a.get("brief", "new project"))
            if len(brief) > 8000:
                raise ValueError("Project brief is too long")
            template = a.get("template", "python" if "python" in brief.lower() else "website")
            if template not in {"python", "website"}:
                raise ValueError("Supported templates are Python and website")
            project = new_project(Path(self.settings.projects_root), brief, template)
            return Result(f"Created a {template} scaffold at {project}. The requested features are recorded in TASK.md.", project=project, needs_ai=brief if k == "code_project" else None)
        if k == "dictate":
            return self.dictate(str(a["text"]), target_window)
        if k == "system":
            operation = a["operation"]
            if operation == "lock":
                if not ctypes.windll.user32.LockWorkStation():
                    raise OSError("Windows did not accept the lock request")
            elif operation in {"shutdown", "restart"}:
                subprocess.run([str(Path(os.environ["WINDIR"]) / "System32" / "shutdown.exe"), "/s" if operation == "shutdown" else "/r", "/t", "30"], check=True, creationflags=NO_WINDOW)
            else:
                raise ValueError("Unsupported system action")
            return Result(f"Requested {operation}." + (" Windows will wait 30 seconds; use shutdown /a to cancel." if operation != "lock" else ""))
        raise ValueError("This action is not implemented")

    @staticmethod
    def open_path(path: Path) -> Result:
        if not path.exists():
            raise ValueError(f"This location does not exist: {path}")
        os.startfile(str(path))
        return Result(f"Asked Windows to open {path.name}.")

    def open_app(self, target: str, name: str) -> Result:
        if target == "@browser":
            os.startfile("https://www.google.com")
        elif target == "@vscode":
            candidates = [Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Microsoft VS Code/Code.exe", Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Microsoft VS Code/Code.exe"]
            path = next((p for p in candidates if p.is_file()), None)
            if path:
                subprocess.Popen([str(path)], creationflags=NO_WINDOW)
            else:
                raise ValueError("VS Code was not found. Add its executable in Settings → Apps.")
        elif target == "@codex":
            response = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "Get-StartApps | Where-Object {$_.Name -match 'Codex'} | Select-Object -First 1 -ExpandProperty AppID"], capture_output=True, text=True, timeout=15, creationflags=NO_WINDOW)
            appid = response.stdout.strip()
            if not appid or any(c in appid for c in '\r\n"'):
                raise ValueError("Codex was not found in Start apps. Register its executable in Settings → Apps.")
            subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + appid], creationflags=NO_WINDOW)
        elif target in {"calc.exe", "notepad.exe", "mspaint.exe", "explorer.exe"}:
            subprocess.Popen([str(Path(os.environ["WINDIR"]) / "System32" / target)], creationflags=NO_WINDOW)
        elif target == "ms-settings:":
            os.startfile(target)
        elif self.settings.app_aliases.get(name) == target:
            p = Path(target).expanduser().resolve()
            if not p.is_file() or p.suffix.lower() not in {".exe", ".lnk"}:
                raise ValueError("Registered app must be an existing .exe or .lnk")
            os.startfile(str(p))
        else:
            raise ValueError("Application is not registered")
        return Result(f"Asked Windows to open {name}.")

    def find_media(self, query: str) -> Result:
        if not self.settings.media_folders:
            return Result("Choose your movie folders in Settings first.")
        query = query.lower().strip()
        if not query:
            raise ValueError("Tell me the movie title")
        matches = []
        visited = 0
        for folder in self.settings.media_folders:
            root = Path(folder).expanduser().resolve()
            if not root.is_dir():
                continue
            for directory, dirs, files in os.walk(root, followlinks=False):
                dirs[:] = [d for d in dirs if not self._reparse(Path(directory) / d)]
                for f in files:
                    visited += 1
                    if visited > 20000:
                        break
                    p = Path(directory) / f
                    if p.suffix.lower() not in VIDEO_EXTENSIONS or self._reparse(p):
                        continue
                    stem = p.stem.lower().replace(".", " ").replace("_", " ")
                    score = 1.0 if query in stem else difflib.SequenceMatcher(None, query, stem).ratio()
                    if score >= 0.62:
                        matches.append((score, p))
                if visited > 20000:
                    break
        matches.sort(key=lambda x: (-x[0], str(x[1]).lower()))
        if not matches:
            return Result(f"No matching local movie found for {query}.")
        if len(matches) == 1:
            return self.execute(Action("open_media", {"path": str(matches[0][1])}))
        choices = [(f"{p.name} — {p.parent.name}", Action("open_media", {"path": str(p)})) for _, p in matches[:8]]
        return Result("Several movies match. Choose a file below or say its number.", choices=choices)

    @staticmethod
    def _reparse(path: Path) -> bool:
        try:
            return bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
        except OSError:
            return True

    @staticmethod
    def dictate(text: str, target: int) -> Result:
        if not target or not ctypes.windll.user32.IsWindow(ctypes.c_void_p(target)):
            raise ValueError("Activate Jeru with Ctrl+Alt+J from the app you want to type into")
        import win32clipboard
        import win32con
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
        finally:
            win32clipboard.CloseClipboard()
        if not ctypes.windll.user32.SetForegroundWindow(ctypes.c_void_p(target)):
            raise ValueError("Could not focus the target app. Your text is on the clipboard.")
        keypress(0x56, 0x11)
        return Result("Sent your text to the selected app. The clipboard now contains the dictated text.")
