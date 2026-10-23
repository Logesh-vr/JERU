from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urlencode


@dataclass(frozen=True)
class Action:
    kind: str
    args: dict = field(default_factory=dict)


SITES = {
    "youtube": "https://www.youtube.com", "you tube": "https://www.youtube.com",
    "யூடியூப்": "https://www.youtube.com", "யூ டியூப்": "https://www.youtube.com",
    "யூடியூப்பை": "https://www.youtube.com", "யூடியூபை": "https://www.youtube.com", "google": "https://www.google.com",
    "யூட்யூப்": "https://www.youtube.com", "யூட்யூப்பை": "https://www.youtube.com",
    "யூடியூப்ப": "https://www.youtube.com", "யூடுப்": "https://www.youtube.com",
    "github": "https://github.com", "netflix": "https://www.netflix.com",
    "gmail": "https://mail.google.com", "whatsapp": "https://web.whatsapp.com",
}
FOLDERS = {
    "downloads": "Downloads", "download": "Downloads", "டவுன்லோட்ஸ்": "Downloads",
    "documents": "Documents", "desktop": "Desktop", "pictures": "Pictures",
    "videos": "Videos", "movies": "Videos", "music": "Music",
    "movies folder": "Videos", "projects": "@projects",
}
APPS = {
    "calculator": "calc.exe", "கால்குலேட்டர்": "calc.exe", "notepad": "notepad.exe",
    "paint": "mspaint.exe", "explorer": "explorer.exe", "file explorer": "explorer.exe",
    "settings": "ms-settings:", "vs code": "@vscode", "vscode": "@vscode",
    "visual studio code": "@vscode", "codex": "@codex", "browser": "@browser",
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).strip().lower()
    text = re.sub(r"^[\s,.:!?]*(?:hey\s+)?(?:jerush|jeru|ஜெரூ|ஜெரு)(?=$|[\s,.:!?])[\s,.:!?]*", "", text)
    return re.sub(r"\s+", " ", text).strip(" .!?,")


def target_text(text: str) -> str:
    # Remove whole command phrases, never arbitrary substrings in names.
    phrases = r"(?:please|can you|could you|open|launch|start|show|my|the|folder|app|pannu|panna|pannunga|thira|thirakkavum|திறந்து வை|திறக்கவும்|திறந்து|திறக்க|திற|விடு|ஓப்பன்|ஓபன்|பண்ணுங்கள்|பண்ணுங்க|பண்ணவும்|பண்ணிடுங்க|பண்ணிடு|பண்ணா|பண்ணு|பண்ண)"
    # Python's \w excludes Tamil vowel signs and pulli marks. Keep those
    # inside word boundaries so a short verb cannot consume part of a name.
    text = re.sub(rf"(?<![\w\u0b80-\u0bff]){phrases}(?![\w\u0b80-\u0bff])", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip(" .!?,\"'")


def parse(text: str, aliases: dict | None = None, app_aliases: dict | None = None) -> Action:
    t = normalize(text)
    if not t:
        return Action("help")
    if t in {"stop", "cancel", "niruthu", "நிறுத்து", "வேண்டாம்", "cancel that"}:
        return Action("cancel")
    if t in {"yes", "confirm", "ஆம்", "aama", "yes do it"}:
        return Action("confirm")
    if t in {"no", "இல்லை", "illa", "never mind"}:
        return Action("cancel")
    if t in {"help", "what can you do", "commands", "உதவி"}:
        return Action("help")
    if t in {"time", "what time is it", "what's the time", "mani enna", "மணி என்ன"}:
        return Action("time")
    if t in {"mute", "unmute", "mute pannu", "மியூட் பண்ணு"}:
        return Action("media", {"key": "mute"})
    if re.search(r"(?:volume|சத்த|sound|ஒலி|வால்யூம்)", t):
        if re.search(r"\b(?:up|increase|raise|kootu|adhigam)\b|அதிக|கூட்டு|உயர்த்து", t):
            return Action("media", {"key": "volume_up"})
        if re.search(r"\b(?:down|decrease|lower|kammi|reduce)\b|குறை|கம்மி", t):
            return Action("media", {"key": "volume_down"})
    if t in {"pause", "play", "resume", "pause it", "pause the movie", "play pannu", "pause pannu", "நிறுத்தி வை"}:
        return Action("media", {"key": "play_pause"})
    if t in {"next", "next track", "next song", "அடுத்த பாடல்"}:
        return Action("media", {"key": "next"})
    if t in {"previous", "previous track", "previous song"}:
        return Action("media", {"key": "previous"})
    if t in {"minimize", "minimize window", "minimize this window"}:
        return Action("window", {"operation": "minimize"})
    if t in {"maximize", "maximize window", "maximize this window"}:
        return Action("window", {"operation": "maximize"})
    if t in {"close window", "close this window"}:
        return Action("window", {"operation": "close"})
    if t in {"switch window", "switch app", "next window"}:
        return Action("window", {"operation": "switch"})
    if re.fullmatch(r"(?:shut\s?down|restart|reboot|lock)(?: (?:the |my )?(?:computer|laptop|pc))?", t):
        return Action("system", {"operation": "lock" if t.startswith("lock") else "restart" if t.startswith(("restart", "reboot")) else "shutdown"})
    m = re.match(r"(?:set (?:a )?timer (?:for )?|timer )?(\d+)\s*(seconds?|minutes?|hours?|நிமிடம்|வினாடி)(?: timer|\s*டைமர்)?$", t)
    if m:
        unit = m[2]
        seconds = int(m[1]) * (3600 if unit.startswith("hour") else 60 if unit.startswith("minute") or unit == "நிமிடம்" else 1)
        return Action("timer", {"seconds": seconds})
    m = re.match(r"(?:take (?:a )?note|note|remember this|குறிப்பு)\s*[:,-]?\s+(.+)", t)
    if m:
        return Action("note", {"text": m[1]})
    m = re.match(r"(?:search (?:on )?youtube (?:for )?|youtube (?:search|la search) )(.+)", t)
    if m:
        return Action("open_url", {"url": "https://www.youtube.com/results?" + urlencode({"search_query": m[1]})})
    m = re.match(r"(?:search (?:google |the web )?(?:for )?|google )(.+)", t)
    if m:
        return Action("open_url", {"url": "https://www.google.com/search?" + urlencode({"q": m[1]})})
    m = re.match(r"(?:play movie|watch movie|watch|play film|play)\s+(.+)", t)
    if m:
        return Action("find_media", {"query": m[1]})
    m = re.match(r"(?:create|make|build|start)\s+(?:a |an )?(python|website|web|html|react)?\s*(?:project|app|website|tool)(?:\s+(?:called|named))?\s*[:,-]?\s*(.*)", t)
    if m:
        kind = m[1] or "website"
        if t.startswith("build "):
            return Action("code_project", {"brief": t[6:]})
        return Action("create_project", {"template": "python" if kind == "python" else "website", "brief": m[2] or "new project"})
    m = re.match(r"(?:build|code|implement)\s+(.+)", t)
    if m:
        return Action("code_project", {"brief": m[1]})
    m = re.match(r"(?:dictate|type this|type)\s*[:,-]?\s+(.+)", t)
    if m:
        # Preserve original casing for dictation.
        original = re.sub(r"^(?:(?:hey\s+)?jeru[,\s]+)?(?:dictate|type this|type)\s*[:,-]?\s+", "", text, flags=re.I)
        return Action("dictate", {"text": original})
    m = re.match(r"run (?:routine )?(.+)", t)
    if m:
        return Action("routine", {"name": m[1]})
    target = target_text(t)
    if target in SITES:
        return Action("open_url", {"url": SITES[target]})
    for name, path in (aliases or {}).items():
        if target == target_text(name.lower()):
            return Action("open_alias", {"name": name, "path": path})
    if target in FOLDERS:
        return Action("open_folder", {"name": FOLDERS[target]})
    for name, path in (app_aliases or {}).items():
        if target == name.lower():
            return Action("open_app", {"target": path, "name": name})
    if target in APPS:
        return Action("open_app", {"target": APPS[target], "name": target})
    return Action("unknown", {"text": text})


MODEL_ACTIONS = {
    "open_url": {"url"}, "open_folder": {"name"}, "media": {"key"},
    # Saving a note requires an explicit registered note command above.
    # Unknown speech must never become stored text invented by the model.
    "find_media": {"query"}, "timer": {"seconds"},
    "create_project": {"template", "brief"}, "code_project": {"brief"},
    "time": set(), "help": set(), "say": {"text"},
}


def validate_model_action(obj: dict) -> Action:
    if not isinstance(obj, dict) or obj.get("kind") not in MODEL_ACTIONS:
        raise ValueError("The local model proposed an unsupported action")
    kind, args = obj["kind"], obj.get("args", {})
    if not isinstance(args, dict) or set(args) != MODEL_ACTIONS[kind]:
        raise ValueError("The local model supplied invalid action arguments")
    if any(not isinstance(v, (str, int, float)) or isinstance(v, bool) for v in args.values()):
        raise ValueError("Invalid action argument type")
    if any(isinstance(v, str) and len(v) > 8000 for v in args.values()):
        raise ValueError("Action argument too long")
    return Action(kind, args)
