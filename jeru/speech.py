from __future__ import annotations

import queue
import re
import subprocess
import threading
import time
from pathlib import Path

from .config import Settings, app_root


TAMIL_VOICE = "ta+f3"


def select_female_english_voice(sapi):
    """Select an installed offline voice by metadata, never the male default."""
    for token in sapi.GetVoices():
        try:
            languages = token.GetAttribute("Language").split(";")
            english = any(int(code, 16) & 0x3ff == 9 for code in languages)
            if token.GetAttribute("Gender").casefold() == "female" and english:
                sapi.Voice = token
                return {"name": token.GetDescription(), "gender": "Female", "id": token.Id}
        except (ValueError, TypeError):
            continue
    raise ValueError("No offline female English voice is installed. Responses remain available as text.")


def spoken_reply(text: str, language: str) -> str:
    if language != "ta":
        return text
    # Short local responses do not need a translation model.
    if text.startswith("Opened the link"):
        return "இணைப்பை உங்கள் உலாவிக்கு அனுப்பிவிட்டேன்."
    if text.startswith("Asked Windows to open"):
        return "திறக்க சொல்லிவிட்டேன்."
    if text.startswith("Saved your note"):
        return "உங்கள் குறிப்பை சேமித்துவிட்டேன்."
    if text.startswith("Sent "):
        return "கட்டளையை அனுப்பிவிட்டேன்."
    if text.startswith("Timer set"):
        return "டைமர் வைத்துவிட்டேன். ஜெருவை திறந்து வைத்திருங்கள்."
    if text.startswith("Created a "):
        return "புதிய திட்டத்திற்கான கோப்புறையை உருவாக்கிவிட்டேன்."
    if text.startswith("Several movies"):
        return "ஒன்றுக்கு மேல் திரைப்படங்கள் உள்ளன. எந்தக் கோப்பை திறக்க வேண்டும்?"
    if text.startswith("No matching local movie"):
        return "அந்தத் திரைப்படம் கிடைக்கவில்லை."
    if text.startswith("Cancelled"):
        return "ரத்து செய்துவிட்டேன்."
    return text


class Speaker(threading.Thread):
    def __init__(self, settings: Settings, on_status=lambda text: None):
        super().__init__(daemon=True, name="jeru-speaker")
        self.settings = settings
        self.on_status = on_status
        self.messages = queue.Queue()
        self.busy = threading.Event()
        self.cancelled = threading.Event()
        self.finished = threading.Event()
        self.start()

    def say(self, text: str):
        if self.settings.speak:
            self.messages.put(text[:1200])

    def cancel(self):
        self.cancelled.set()
        while True:
            try:
                self.messages.get_nowait()
            except queue.Empty:
                break

    def stop(self):
        self.finished.set()
        self.cancel()
        self.messages.put(None)

    @staticmethod
    def espeak() -> Path | None:
        candidates = [app_root() / "runtimes/espeak-ng/espeak-ng.exe", Path("C:/Program Files/eSpeak NG/espeak-ng.exe"), Path("C:/Program Files (x86)/eSpeak NG/espeak-ng.exe")]
        return next((p for p in candidates if p.is_file()), None)

    def run(self):
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        sapi = None
        try:
            try:
                sapi = win32com.client.Dispatch("SAPI.SpVoice")
                select_female_english_voice(sapi)
                sapi.Rate = 1
            except Exception as exc:
                sapi = None
                self.on_status("Offline female English voice unavailable: " + str(exc)[:160])
            while not self.finished.is_set():
                text = self.messages.get()
                if text is None:
                    break
                self.cancelled.clear()
                self.busy.set()
                try:
                    text = spoken_reply(text, self.settings.reply_language)
                    if re.search(r"[\u0b80-\u0bff]", text):
                        exe = self.espeak()
                        if not exe:
                            self.on_status("Tamil speech pack is missing. The response is available as text.")
                            continue
                        process = subprocess.Popen([str(exe), "--path=" + str(exe.parent), "-v", TAMIL_VOICE, "-s", "145", "--stdin"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                        process.stdin.write(text.encode("utf-8"))
                        process.stdin.close()
                        while process.poll() is None:
                            if self.cancelled.wait(0.08) or self.finished.is_set():
                                process.kill()
                                process.wait()
                                break
                    elif sapi:
                        sapi.Speak(text, 1)
                        while not sapi.WaitUntilDone(80):
                            if self.cancelled.is_set() or self.finished.is_set():
                                sapi.Speak("", 3)
                                break
                except Exception as exc:
                    self.on_status("Speech output: " + str(exc)[:160])
                finally:
                    # Allow speaker echo to decay before accepting a wake phrase.
                    self.cancelled.wait(0.25)
                    self.busy.clear()
        finally:
            self.busy.clear()
            pythoncom.CoUninitialize()
