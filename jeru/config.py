from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


def app_root() -> Path:
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


def data_root() -> Path:
    override = os.environ.get("JERU_DATA_DIR")
    return Path(override).resolve() if override else Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Jeru"


@dataclass
class Settings:
    model_root: str = ""
    projects_root: str = ""
    language: str = "auto"
    reply_language: str = "en"
    microphone: int | None = None
    speak: bool = True
    wake_enabled: bool = True
    backlight_enabled: bool = True
    backlight_level: int = 2
    speech_threshold: float = 0.012
    silence_seconds: float = 1.1
    max_record_seconds: float = 24.0
    aliases: dict[str, str] = field(default_factory=dict)
    app_aliases: dict[str, str] = field(default_factory=dict)
    media_folders: list[str] = field(default_factory=list)
    routines: dict[str, list[str]] = field(default_factory=lambda: {"study mode": ["open vs code", "open documents"]})
    keep_history: bool = False
    start_with_windows: bool = False

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or data_root() / "settings.json"
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(obj, dict):
                raise ValueError("Settings must be a JSON object")
            allowed = cls.__dataclass_fields__
            config = cls(**{k: v for k, v in obj.items() if k in allowed})
        except (OSError, ValueError, TypeError):
            config = cls()
        config.model_root = config.model_root or str(app_root() / "models")
        config.projects_root = config.projects_root or str(Path.home() / "Documents" / "Jeru Projects")
        config.language = config.language if isinstance(config.language, str) and config.language in {"auto", "en", "ta"} else "auto"
        config.reply_language = config.reply_language if isinstance(config.reply_language, str) and config.reply_language in {"en", "ta"} else "en"
        def bounded(value, default, lower, upper):
            try:
                number = float(value)
                import math
                return max(lower, min(upper, number)) if math.isfinite(number) else default
            except (ValueError, TypeError):
                return default
        config.backlight_level = int(bounded(config.backlight_level, 2, 1, 2))
        config.speech_threshold = bounded(config.speech_threshold, 0.012, 0.002, 0.15)
        config.silence_seconds = bounded(config.silence_seconds, 1.1, 0.5, 3.0)
        config.max_record_seconds = bounded(config.max_record_seconds, 24, 5, 90)
        if not isinstance(config.model_root, str):
            config.model_root = str(app_root() / "models")
        if not isinstance(config.projects_root, str):
            config.projects_root = str(Path.home() / "Documents" / "Jeru Projects")
        if type(config.microphone) is not int:
            config.microphone = None
        for name in ("aliases", "app_aliases", "routines"):
            if not isinstance(getattr(config, name), dict):
                setattr(config, name, {})
        if not isinstance(config.media_folders, list):
            config.media_folders = []
        config.media_folders = [p for p in config.media_folders if isinstance(p, str)]
        for key in ("aliases", "app_aliases"):
            setattr(config, key, {k: v for k, v in getattr(config, key).items() if isinstance(k, str) and isinstance(v, str)})
        return config

    def save(self, path: Path | None = None) -> None:
        path = path or data_root() / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    @property
    def models(self) -> Path:
        return Path(self.model_root)


def offline_environment() -> None:
    # Model code receives only explicit local paths. No implicit Hub downloads.
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY", "DO_NOT_TRACK"):
        os.environ[key] = "1"
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ.setdefault("HF_HOME", str(data_root() / "model-cache"))
