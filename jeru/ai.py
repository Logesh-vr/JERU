from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from .config import Settings, app_root
from .intents import Action, validate_model_action
from .projects import validate_generated_files


class LocalBrain:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()

    @property
    def ready(self) -> bool:
        return bool(self.model_files())

    def model_files(self) -> list[Path]:
        folder = self.settings.models / "brain"
        try:
            manifest = json.loads((folder / "jeru-manifest.json").read_text(encoding="utf-8"))
            files = [folder / name for name in manifest["sha256"] if name.endswith(".gguf") and Path(name).name == name]
            if files and all(p.is_file() for p in files):
                return files
        except (OSError, ValueError, TypeError, KeyError):
            pass
        return sorted(folder.glob("*.gguf"))

    def cancel(self) -> None:
        with self._lock:
            if self._process and self._process.poll() is None:
                self._process.kill()

    def request(self, mode: str, text: str) -> dict:
        models = self.model_files()
        if not models:
            raise ValueError("No local AI model is installed. Choose your model folder in Settings or run the one-time model setup.")
        command = [sys.executable, "--ai-worker"] if getattr(sys, "frozen", False) else [sys.executable, "-m", "jeru.ai_worker"]
        env = os.environ.copy()
        env.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "DO_NOT_TRACK": "1"})
        with self._lock:
            process = subprocess.Popen(command, cwd=str(app_root()), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self._process = process
        try:
            stdout, stderr = process.communicate(json.dumps({"mode": mode, "text": text[:8000], "model": str(models[0])}), timeout=240)
            if process.returncode:
                error = stderr.strip().splitlines()[-1:] or ["The local model worker stopped"]
                raise ValueError(error[0][:350])
            result = json.loads(stdout)
            if "error" in result:
                raise ValueError(result["error"])
            return result
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise ValueError("The local model took too long. Try a shorter request or smaller model.") from None
        finally:
            with self._lock:
                if self._process is process:
                    self._process = None

    def interpret(self, text: str) -> Action:
        return validate_model_action(self.request("action", text))

    def generate(self, text: str) -> dict[str, str]:
        return validate_generated_files(self.request("code", text))
