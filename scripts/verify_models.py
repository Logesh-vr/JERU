import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent / "models"
for component in ("speech", "wake", "brain"):
    folder = root / component
    manifest_path = folder / "jeru-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name, expected in manifest["sha256"].items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder.resolve()) or not path.is_file():
            raise ValueError(f"Missing or unsafe model file: {component}/{name}")
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected:
            raise ValueError(f"Model checksum mismatch: {component}/{name}")
    print(f'{component}: {len(manifest["sha256"])} files verified')
