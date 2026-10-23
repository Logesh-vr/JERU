"""Resolve Windows wheels using public PyPI metadata, without downloading payloads."""
import json
import platform
import urllib.request
from collections import deque
from pathlib import Path

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import sys_tags
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version

initial = ["PySide6-Essentials>=6.8,<7", "sounddevice>=0.5,<1", "numpy>=2,<3", "faster-whisper>=1.2,<2", "sherpa-onnx>=1.12,<2", "sentencepiece>=0.2,<1", "pywin32>=310", "pyinstaller>=6,<7", "pytest>=8,<10", "psutil>=7,<8", "diskcache>=5.6.1", "jinja2>=2.11.3"]
tag_order = {tag: i for i, tag in enumerate(sys_tags())}
tags = set(tag_order)
constraints, selected, cache = {}, {}, {}
pending = deque(Requirement(r) for r in initial)
PINS = dict(pair.split("==", 1) for pair in """pyside6-essentials==6.12.0 shiboken6==6.12.0 sounddevice==0.5.6 numpy==2.4.6 faster-whisper==1.2.1 sherpa-onnx==1.13.8 sherpa-onnx-core==1.13.8 sentencepiece==0.2.2 pywin32==312 pyinstaller==6.22.3 pytest==9.1.1 psutil==7.2.2 diskcache==5.6.3 jinja2==3.1.6 cffi==2.1.1 ctranslate2==4.8.3 huggingface-hub==2.2.0 tokenizers==0.23.3 onnxruntime==1.31.0 av==18.1.0 tqdm==4.70.1 altgraph==0.17.5 packaging==26.3 pefile==2024.8.26 pyinstaller-hooks-contrib==2026.8 pywin32-ctypes==0.2.3 colorama==0.4.6 iniconfig==2.3.1 pluggy==1.7.0 pygments==2.21.0 markupsafe==3.0.4 pyyaml==6.0.3 click==8.5.0 filelock==4.2.1 fsspec==2026.9.0 hf-xet==1.7.0 httpx2==2.13.1 typing-extensions==4.16.0 flatbuffers==25.12.19 protobuf==7.36.2 pycparser==3.11 anyio==4.15.1 httpcore2==2.13.1 idna==3.20 truststore==0.10.5 h11==0.16.0 setuptools==80.9.0""".split())


def metadata(name, version=None):
    key = (name, version)
    if key not in cache:
        suffix = f"/{version}" if version else ""
        with urllib.request.urlopen(f"https://pypi.org/pypi/{name}{suffix}/json", timeout=40) as r:
            cache[key] = json.load(r)
    return cache[key]


while pending:
    requirement = pending.popleft()
    if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
        continue
    name = canonicalize_name(requirement.name)
    constraints.setdefault(name, set()).add(str(requirement.specifier))
    spec = SpecifierSet(",".join(s for s in constraints[name] if s))
    if name in selected and Version(selected[name]["metadata"]["version"]) in spec:
        continue
    pinned = PINS.get(name)
    info = metadata(name, pinned)
    versions = [Version(pinned)] if pinned else sorted((Version(v) for v in info["releases"] if not Version(v).is_prerelease and Version(v) in spec), reverse=True)
    chosen = None
    for version in versions:
        candidates = []
        if version not in spec:
            raise RuntimeError(f"Pinned {name} {version} violates {spec}")
        for file in info["urls"] if pinned else info["releases"][str(version)]:
            if file["packagetype"] != "bdist_wheel" or file.get("yanked"):
                continue
            if file.get("requires_python") and platform.python_version() not in SpecifierSet(file["requires_python"]):
                continue
            if tags.intersection(parse_wheel_filename(file["filename"])[3]):
                candidates.append(file)
        if candidates:
            chosen = min(candidates, key=lambda file: min(tag_order[t] for t in parse_wheel_filename(file["filename"])[3] if t in tags))
            break
    if not chosen:
        raise RuntimeError(f"No compatible wheel for {name}{spec}")
    detail = metadata(name, str(version))
    selected[name] = {"metadata": {"name": name, "version": str(version)}, "download_info": {"url": chosen["url"], "archive_info": {"hashes": {"sha256": chosen["digests"]["sha256"]}}}}
    print(name, version, flush=True)
    for dependency in detail["info"].get("requires_dist") or []:
        pending.append(Requirement(dependency))

out = Path(__file__).resolve().parent.parent / "artifacts/dependencies.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"install": list(selected.values())}, indent=2), encoding="utf-8")
print(f"Resolved {len(selected)} wheels without fetching binary payloads", flush=True)
