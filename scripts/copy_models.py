"""Copy only manifest-listed model files, never interrupted downloads."""
import json
import shutil
from pathlib import Path

root = Path(__file__).resolve().parent.parent
for component in ("speech", "wake", "brain"):
    source = root / "models" / component
    manifest = source / "jeru-manifest.json"
    info = json.loads(manifest.read_text(encoding="utf-8"))
    target = root / "dist/Jeru/models" / component
    target.mkdir(parents=True, exist_ok=True)
    for name in [*info["sha256"], "jeru-manifest.json"]:
        path = (source / name).resolve()
        if not path.is_relative_to(source.resolve()) or not path.is_file():
            raise ValueError("Unsafe or missing model file: " + name)
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    print(component, "copied", len(info["sha256"]), "model files")
