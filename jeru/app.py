from __future__ import annotations

import ctypes
import datetime as dt
import hashlib
import json
import logging
import os
import sys
import threading
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QTimer, Signal, Qt
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QSystemTrayIcon

from .actions import Executor, Result, foreground_window, needs_confirmation, session_unlocked
from .ai import LocalBrain
from .config import Settings, app_root, data_root, offline_environment
from .intents import Action, normalize, parse
from .lighting import LightingController
from .projects import write_generated
from .speech import Speaker
from .ui import SettingsDialog, Window, icon, load_fonts
from .voice import VoiceEngine


class Events(QObject):
    result = Signal(int, object)
    error = Signal(int, str)
    progress = Signal(int, str)
    light_status = Signal(str)
    speech_status = Signal(str)
    project_created = Signal(int, str)


class Hotkeys(QAbstractNativeEventFilter):
    def __init__(self, controller, enabled=True):
        super().__init__()
        self.controller = controller
        self.registered = []
        for ident, key in ((1, 0x4A), (2, 0x4B)) if enabled else ():
            if ctypes.windll.user32.RegisterHotKey(None, ident, 0x4003, key):
                self.registered.append(ident)

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) in {b"windows_generic_MSG", b"windows_dispatcher_MSG"}:
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312:
                if msg.wParam == 1:
                    self.controller.activate()
                elif msg.wParam == 2:
                    self.controller.cancel()
                return True, 0
        return False, 0

    def close(self):
        for ident in self.registered:
            ctypes.windll.user32.UnregisterHotKey(None, ident)


class Controller(QObject):
    def __init__(self, app: QApplication, window: Window, settings: Settings):
        super().__init__()
        self.app, self.window, self.settings = app, window, settings
        self.events = Events()
        self.events.result.connect(self.completed)
        self.events.error.connect(self.failed)
        self.events.progress.connect(self.progress)
        self.events.light_status.connect(window.light_status.setText)
        self.events.speech_status.connect(window.model_status.setText)
        self.events.project_created.connect(self.project_created)
        self.executor = Executor(settings)
        self.brain = LocalBrain(settings)
        self.speaker = Speaker(settings, self.events.speech_status.emit)
        self.lighting = LightingController(self.events.light_status.emit)
        self.voice = VoiceEngine(settings, self.speaker.busy)
        self.voice.events.state.connect(self.voice_state)
        self.voice.events.transcript.connect(self.submit)
        self.voice.events.level.connect(self.set_level)
        self.voice.events.error.connect(self.voice_error)
        self.voice.events.status.connect(window.model_status.setText)
        self.voice.events.activated.connect(self.capture_target)
        self.busy, self.job, self.target = False, 0, 0
        self.pending: Action | None = None
        self.pending_deadline = None
        self.choices = []
        self.timers = []
        self.last_project: Path | None = None
        self.turn_cancelled = threading.Event()
        window.listen.connect(self.activate)
        window.pause.connect(self.pause)
        window.stop.connect(self.cancel)
        window.submitted.connect(self.submit)
        window.settings_requested.connect(self.show_settings)
        window.confirmed.connect(self.confirm)
        window.choice_selected.connect(self.choose)
        window.project_requested.connect(self.open_project)
        self.tray = QSystemTrayIcon(icon(), self)
        self.tray.setToolTip("Jeru · microphone paused")
        menu = QMenu()
        menu.addAction("Show Jeru", self.show)
        menu.addAction("Listen · Ctrl+Alt+J", self.activate)
        menu.addAction("Pause microphone", self.pause)
        menu.addAction("Stop task · Ctrl+Alt+K", self.cancel)
        menu.addSeparator()
        menu.addAction("Settings", self.show_settings)
        menu.addAction("Quit Jeru", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()
        self.hotkeys = Hotkeys(self, enabled=os.environ.get("JERU_TEST_MODE") != "1")
        app.installNativeEventFilter(self.hotkeys)
        self.lock_timer = QTimer(self)
        self.lock_timer.timeout.connect(self.check_lock)
        self.lock_timer.start(1500)
        self.update_components()
        app.aboutToQuit.connect(self.cleanup)

    def show(self):
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def capture_target(self):
        current = foreground_window()
        if current and current != int(self.window.winId()):
            self.target = current

    def activate(self):
        if self.busy:
            self.window.log("Jeru", "A task is running. Stop it before starting another command.")
            return
        self.capture_target()
        self.speaker.cancel()
        self.voice.suspended.clear()
        self.voice.activate()
        self.tray.setToolTip("Jeru · microphone enabled")

    def start_wake(self):
        # Sign-in startup enables keyword detection, not an unsolicited turn.
        if not self.busy:
            self.voice.manual.clear()
            self.voice.cancelled.clear()
            self.voice.suspended.clear()
            self.voice.enabled.set()
            self.tray.setToolTip("Jeru · waiting for its name")

    def pause(self):
        self.voice.pause()
        self.lighting.listening(False)
        self.window.set_state("Microphone paused")
        self.tray.setToolTip("Jeru · microphone paused")

    def cancel(self):
        self.job += 1
        self.turn_cancelled.set()
        self.brain.cancel()
        self.speaker.cancel()
        self.voice.cancel_turn()
        self.voice.suspended.clear()
        self.lighting.listening(False)
        self.busy = False
        self.pending, self.choices = None, []
        self.window.confirm_box.hide()
        self.window.choices.hide()
        self.window.set_state("Stopped")
        self.window.log("Jeru", "Cancelled pending work. Already completed actions cannot be undone.")

    def check_lock(self):
        if not session_unlocked():
            if self.pending:
                self.pending = None
                self.window.confirm_box.hide()
            if self.voice.enabled.is_set() or self.busy:
                self.cancel()
                self.pause()
                self.window.set_state("Paused · Windows locked")
        if self.pending and dt.datetime.now() > self.pending_deadline:
            self.pending = None
            self.window.confirm_box.hide()
            self.window.log("Jeru", "Confirmation expired. Repeat the instruction if you still want it.")

    def voice_state(self, state):
        self.lighting.listening(state == "Listening" and self.settings.backlight_enabled, self.settings.backlight_level)
        if not self.busy:
            self.window.set_state(state)

    def set_level(self, level):
        self.window.orb.level = level

    def voice_error(self, text):
        self.lighting.listening(False)
        self.window.log("Microphone", text)
        self.window.model_status.setText(text)
        self.window.set_state("Microphone paused")

    def submit(self, text: str):
        if not session_unlocked():
            self.pause()
            return
        self.window.log("You", text)
        action = parse(text, self.settings.aliases, self.settings.app_aliases)
        if action.kind == "cancel":
            self.cancel()
            return
        if action.kind == "confirm":
            self.confirm()
            return
        t = normalize(text)
        numbers = {"one": 0, "first": 0, "first one": 0, "ஒன்று": 0, "two": 1, "second": 1, "second one": 1, "இரண்டு": 1, "three": 2, "third": 2, "மூன்று": 2}
        if self.choices and (t in numbers or t.isdigit()):
            self.choose(numbers[t] if t in numbers else int(t)-1)
            return
        if self.busy:
            self.window.log("Jeru", "A task is already running. Say Stop or use Ctrl+Alt+K to cancel it.")
            return
        # Any unrelated request invalidates a prior destructive confirmation.
        self.pending = None
        self.window.confirm_box.hide()
        self.choices = []
        self.window.choices.hide()
        if needs_confirmation(action):
            self.pending = action
            self.pending_deadline = dt.datetime.now() + dt.timedelta(seconds=30)
            detail = json.dumps(action.args, ensure_ascii=False)
            if action.kind in {"window", "dictate"}:
                title = ctypes.create_unicode_buffer(260)
                if self.target:
                    ctypes.windll.user32.GetWindowTextW(ctypes.c_void_p(self.target), title, 260)
                detail += f" · Target: {title.value or 'no application captured'}"
            self.window.confirm_text.setText(f"Confirm {action.kind}: {detail[:500]}")
            self.window.confirm_box.show()
            self.window.set_state("Waiting for confirmation")
            self.voice.suspended.clear()
            self.speaker.say("Please confirm the action shown in Jeru. Say yes, or cancel.")
            return
        self.run_action(action)

    def confirm(self):
        if not self.pending or dt.datetime.now() > self.pending_deadline or not session_unlocked():
            self.window.log("Jeru", "There is no current action to confirm.")
            return
        action, self.pending = self.pending, None
        self.window.confirm_box.hide()
        self.run_action(action)

    def choose(self, index):
        if not 0 <= index < len(self.choices):
            self.window.log("Jeru", "Choose one of the listed numbers.")
            return
        action = self.choices[index][1]
        self.choices = []
        self.window.choices.hide()
        self.run_action(action)

    def run_action(self, action):
        self.busy = True
        self.voice.suspended.set()
        self.lighting.listening(False)
        self.job += 1
        job = self.job
        cancelled = threading.Event()
        self.turn_cancelled = cancelled
        self.window.set_state("Thinking locally" if action.kind == "unknown" else "Working")
        target = self.target
        def work():
            try:
                if cancelled.is_set():
                    return
                selected = action
                if selected.kind == "unknown":
                    selected = self.brain.interpret(selected.args["text"])
                    if cancelled.is_set():
                        return
                if not session_unlocked() or cancelled.is_set():
                    raise ValueError("Task stopped because the session was locked or cancelled")
                if selected.kind == "routine":
                    steps = self.settings.routines.get(selected.args["name"])
                    if not isinstance(steps, list) or not 1 <= len(steps) <= 8:
                        raise ValueError("This routine is not saved. Routines contain 1–8 registered commands.")
                    actions = [parse(t, self.settings.aliases, self.settings.app_aliases) for t in steps]
                    allowed = {"open_url", "open_folder", "open_alias", "open_app", "media", "time", "note"}
                    if any(a.kind not in allowed for a in actions):
                        raise ValueError("Routines support ordinary registered commands only")
                    messages = []
                    for step in actions:
                        if cancelled.is_set() or not session_unlocked():
                            return
                        try:
                            result = self.executor.execute(step, target)
                        except Exception as exc:
                            raise ValueError(f"Routine stopped after {len(messages)} of {len(actions)} steps. {exc}") from exc
                        messages.append(result.message)
                    result = Result("Routine completed. " + " ".join(messages))
                else:
                    result = self.executor.execute(selected, target)
                if result.project:
                    self.events.project_created.emit(job, str(result.project))
                if result.needs_ai:
                    self.events.progress.emit(job, result.message + " Generating source locally…")
                    if cancelled.is_set():
                        return
                    files = self.brain.generate(result.needs_ai)
                    if cancelled.is_set():
                        return
                    issues = write_generated(result.project, files)
                    result.message = f"Generated {len(files)} source files in {result.project / 'generated-proposal'}. " + (f"Found {len(issues)} static issues. " if issues else "Applicable Python/JSON syntax checks passed. ") + "Read GENERATION_REPORT.md. Generated code has not been executed."
                if not cancelled.is_set():
                    self.events.result.emit(job, result)
            except Exception as exc:
                if not cancelled.is_set():
                    self.events.error.emit(job, str(exc))
        threading.Thread(target=work, daemon=True, name=f"jeru-task-{job}").start()

    def progress(self, job, text):
        if job == self.job:
            self.window.log("Jeru", text)
            self.window.set_state("Generating locally")

    def project_created(self, job, path):
        if job == self.job:
            self.last_project = Path(path)
            self.window.project_button.show()

    def open_project(self):
        if self.last_project:
            try:
                Executor.open_path(self.last_project)
            except Exception as exc:
                self.window.log("Project", str(exc))

    def completed(self, job, result):
        if job != self.job:
            return
        self.busy = False
        self.window.log("Jeru", result.message)
        self.window.set_state("Done")
        self.last_project = result.project or self.last_project
        self.choices = result.choices
        if self.choices:
            self.window.choices.clear()
            self.window.choices.addItems([f"{i+1}. {label}" for i, (label, _) in enumerate(self.choices)])
            self.window.choices.show()
        if result.timer_seconds:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: self.alarm(timer))
            timer.start(result.timer_seconds * 1000)
            self.timers.append(timer)
        self.speaker.say(result.message)
        self.voice.suspended.clear()
        if self.settings.keep_history:
            with (data_root() / "history.jsonl").open("a", encoding="utf-8") as history:
                history.write(json.dumps({"time": dt.datetime.now().isoformat(), "result": result.message}, ensure_ascii=False) + "\n")

    def failed(self, job, text):
        if job != self.job:
            return
        self.busy = False
        self.window.log("Jeru", text)
        self.window.set_state("Needs attention")
        self.voice.suspended.clear()
        self.lighting.listening(False)
        self.speaker.say(text)

    def alarm(self, timer):
        self.window.log("Timer", "Your timer has finished.")
        self.tray.showMessage("Jeru timer", "Your timer has finished.")
        self.speaker.say("Your timer has finished.")
        self.timers.remove(timer)
        timer.deleteLater()

    def show_settings(self):
        if self.busy:
            self.window.log("Jeru", "Finish or stop the current task before changing settings.")
            return
        self.pause()
        self.pending = None
        self.window.confirm_box.hide()
        old_startup = self.settings.start_with_windows
        dialog = SettingsDialog(self.settings, self.window)
        dialog.helper_requested.connect(self.lighting.enable_helper)
        dialog.test_light_requested.connect(self.test_light)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            dialog.apply()
            if old_startup != self.settings.start_with_windows:
                try:
                    from .startup import set_startup
                    set_startup(self.settings.start_with_windows)
                except Exception as exc:
                    self.settings.start_with_windows = old_startup
                    self.settings.save()
                    self.window.log("Startup", str(exc))
            self.update_components()
            self.window.log("Settings", "Saved locally. Press Listen to resume with the new settings.")

    def test_light(self):
        self.lighting.listening(True, self.settings.backlight_level)
        QTimer.singleShot(2000, lambda: self.lighting.listening(False))

    def update_components(self):
        root = self.settings.models
        parts = ["Speech ✓" if (root / "speech/model.bin").is_file() else "Speech model missing", "Wake ✓" if (root / "wake/keywords.txt").is_file() else "Wake model missing · hotkey available", "Local AI ✓" if self.brain.ready else "Local AI model missing"]
        from .speech import Speaker
        parts.append("Tamil voice ✓" if Speaker.espeak() else "Tamil voice pack missing")
        self.window.model_status.setText("  ·  ".join(parts))

    def cleanup(self):
        self.turn_cancelled.set()
        self.brain.cancel()
        self.voice.stop()
        self.speaker.stop()
        self.lighting.stop()
        self.lighting.join(timeout=3)
        self.hotkeys.close()
        self.tray.hide()

    def quit(self):
        self.window.really_quit = True
        self.app.quit()


def main():
    offline_environment()
    root = data_root()
    root.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(root / "errors.log"), level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    def exception_hook(exc_type, value, traceback):
        logging.error("Unhandled error", exc_info=(exc_type, value, traceback))
        sys.__excepthook__(exc_type, value, traceback)
    sys.excepthook = exception_hook
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    identity = hashlib.sha256(str(root.resolve()).casefold().encode("utf-8")).hexdigest()[:20]
    mutex = kernel.CreateMutexW(None, False, "Local\\Jeru-" + identity)
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    if ctypes.get_last_error() == 183:
        user = ctypes.windll.user32
        user.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        user.FindWindowW.restype = wintypes.HWND
        handle = user.FindWindowW(None, "Jeru · Local voice assistant")
        if handle:
            user.ShowWindow(ctypes.c_void_p(handle), 9)
            user.SetForegroundWindow(ctypes.c_void_p(handle))
        kernel.CloseHandle(mutex)
        return 0
    app = QApplication(sys.argv)
    load_fonts()
    app.setApplicationName("Jeru")
    app.setOrganizationName("Jeru")
    app.setQuitOnLastWindowClosed(False)
    window = Window()
    controller = Controller(app, window, Settings.load())
    window.show()
    # Keep controller alive for the entire Qt event loop.
    app._jeru_controller = controller
    if "--start-listening" in sys.argv:
        QTimer.singleShot(700, controller.start_wake)
    try:
        return app.exec()
    finally:
        kernel.CloseHandle(mutex)
