"""Explicit online setup only. The Jeru application never imports this module."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import time
import urllib.request
import concurrent.futures
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Jeru-Model-Setup/0.1"}


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as response:
        return json.load(response)


def download(url: str, path: Path, expected: str | None = None) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and expected and hashlib.file_digest(path.open("rb"), "sha256").hexdigest() == expected:
        print("Already verified:", path.name, flush=True)
        return expected
    temporary = path.with_suffix(path.suffix + ".part")
    # Large public model hosts support byte ranges. Keep completed chunks so a
    # connection failure does not restart a multi-gigabyte download.
    try:
        probe = urllib.request.urlopen(urllib.request.Request(url, headers={**UA, "Range": "bytes=0-0"}), timeout=60)
        content_range = probe.headers.get("Content-Range", "")
        status = probe.status
        probe.close()
        size = int(content_range.rsplit("/", 1)[1]) if status == 206 and "/" in content_range else 0
    except (OSError, ValueError):
        size = 0
    if size > 256 * 1024:
        return ranged_download(url, path, size, expected)
    print("Downloading", path.name, flush=True)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as response, temporary.open("wb") as out:
        total = int(response.headers.get("Content-Length", "0"))
        count, last = 0, time.monotonic()
        digest = hashlib.sha256()
        while chunk := response.read(1024 * 1024):
            out.write(chunk)
            digest.update(chunk)
            count += len(chunk)
            if time.monotonic() - last > 15:
                print(f"  {path.name}: {count / 2**20:.0f} / {total / 2**20:.0f} MiB", flush=True)
                last = time.monotonic()
    if total and count != total:
        raise ValueError(f"Incomplete download: {path.name}")
    actual = digest.hexdigest()
    if expected and actual != expected:
        temporary.unlink(missing_ok=True)
        raise ValueError(f"Checksum mismatch: {path.name}")
    temporary.replace(path)
    print("Ready:", path.name, actual, flush=True)
    return actual


def ranged_download(url: str, path: Path, size: int, expected: str | None = None, workers: int = 8) -> str:
    chunk_size = 1024 * 1024
    # Include source identity: base/small speech models share the filename.
    identity = (expected or hashlib.sha256(url.encode()).hexdigest())[:12]
    parts = path.parent / (path.name + ".chunks-1m-" + identity)
    parts.mkdir(exist_ok=True)
    count = (size + chunk_size - 1) // chunk_size
    print(f"Resumable download: {path.name}, {size / 2**20:.0f} MiB, {workers} connections", flush=True)
    def chunk(index):
        start, end = index * chunk_size, min(size - 1, (index + 1) * chunk_size - 1)
        dest = parts / f"{index:05d}"
        if dest.is_file() and dest.stat().st_size == end - start + 1:
            return
        for attempt in range(4):
            try:
                # A different query prevents a proxy caching one range as all ranges.
                sep = "&" if "?" in url else "?"
                request = urllib.request.Request(url + f"{sep}jeru_chunk={index}", headers={**UA, "Range": f"bytes={start}-{end}"})
                with urllib.request.urlopen(request, timeout=120) as response:
                    if response.status != 206 or not response.headers.get("Content-Range", "").startswith(f"bytes {start}-{end}/"):
                        raise ValueError("Server returned an unexpected byte range")
                    with dest.with_suffix(".tmp").open("wb") as out:
                        shutil.copyfileobj(response, out, length=256*1024)
                if dest.with_suffix(".tmp").stat().st_size != end - start + 1:
                    raise ValueError("Incomplete model chunk")
                dest.with_suffix(".tmp").replace(dest)
                return
            except (OSError, ValueError):
                if attempt == 3:
                    raise
                time.sleep(attempt + 1)
    completed, last = 0, time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for future in concurrent.futures.as_completed([pool.submit(chunk, i) for i in range(count)]):
            future.result()
            completed += 1
            if time.monotonic() - last > 15 or completed == count:
                print(f"  {path.name}: {completed}/{count} chunks", flush=True)
                last = time.monotonic()
    temporary = path.with_suffix(path.suffix + ".part")
    digest = hashlib.sha256()
    with temporary.open("wb") as out:
        for index in range(count):
            with (parts / f"{index:05d}").open("rb") as source:
                while data := source.read(1024 * 1024):
                    out.write(data)
                    digest.update(data)
    actual = digest.hexdigest()
    if expected and actual != expected:
        raise ValueError(f"Checksum mismatch: {path.name}")
    temporary.replace(path)
    # Only the explicitly created chunk files under this model's directory.
    for p in parts.iterdir():
        p.unlink()
    parts.rmdir()
    print("Ready:", path.name, actual, flush=True)
    return actual


def model_repo(repo: str, destination: Path, names: list[str]) -> dict:
    info = fetch_json(f"https://huggingface.co/api/models/{repo}?blobs=true")
    commit = info["sha"]
    siblings = {f["rfilename"]: f for f in info["siblings"]}
    files = {}
    for name in names:
        if name not in siblings:
            if name in {"preprocessor_config.json", "README.md", "LICENSE"}:
                continue
            raise ValueError(f"Missing upstream file: {name}")
        expected = siblings[name].get("lfs", {}).get("sha256")
        files[name] = download(f"https://huggingface.co/{repo}/resolve/{commit}/{name}?download=true", destination / name, expected)
    manifest = {"source": repo, "commit": commit, "sha256": files}
    (destination / "jeru-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def speech(models: Path, size="small") -> None:
    model_repo(f"Systran/faster-whisper-{size}", models / "speech", ["model.bin", "config.json", "tokenizer.json", "vocabulary.txt", "preprocessor_config.json", "README.md"])


def keyword(models: Path) -> None:
    import sentencepiece as spm
    name = "sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01"
    archive = models / (name + ".tar.bz2")
    url = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/{name}.tar.bz2"
    digest = download(url, archive)
    target = models / "wake"
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            # Extract only the model's flat files, never links or archive paths.
            base = Path(member.name).name
            if not member.isfile() or base not in {"bpe.model", "tokens.txt", "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx", "decoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx", "decoder-epoch-12-avg-2-chunk-16-left-64.onnx", "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx"}:
                continue
            with tar.extractfile(member) as src, (target / base).open("wb") as dst:
                shutil.copyfileobj(src, dst)
    tokenizer = spm.SentencePieceProcessor(model_file=str(target / "bpe.model"))
    keywords = []
    for phrase in ("JERU", "HEY JERU", "JEROO", "JAY ROO", "JEE ROO"):
        threshold = 0.2 if phrase.startswith("HEY ") else 0.05
        keywords.append(" ".join(tokenizer.encode(phrase, out_type=str)) + f" :3.0 #{threshold}")
    (target / "keywords.txt").write_text("\n".join(keywords) + "\n", encoding="utf-8")
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in target.iterdir() if p.is_file() and p.name != "jeru-manifest.json"}
    (target / "jeru-manifest.json").write_text(json.dumps({"source": url, "archive_sha256": digest, "sha256": files}, indent=2), encoding="utf-8")
    archive.unlink()
    print("Wake model and Jeru keyword list ready", flush=True)


def brain(models: Path, size="4B") -> None:
    # Official publisher quantization; a compact, replaceable first candidate.
    quant = "Q8_0" if size == "0.6B" else "Q4_K_M"
    model_repo(f"Qwen/Qwen3-{size}-GGUF", models / "brain", [f"Qwen3-{size}-{quant}.gguf", "README.md"])


def main() -> None:
    parser = argparse.ArgumentParser(description="One-time downloads for Jeru's offline runtime")
    parser.add_argument("component", choices=["speech", "wake", "brain", "all"])
    parser.add_argument("--models", type=Path, default=ROOT / "models")
    parser.add_argument("--profile", choices=["compact", "balanced", "quality"], default="balanced")
    args = parser.parse_args()
    for name, fn in (("wake", keyword), ("speech", speech), ("brain", brain)):
        if args.component in {name, "all"}:
            if name == "speech":
                speech(args.models, "base" if args.profile == "compact" else "small")
            elif name == "brain":
                brain(args.models, "4B" if args.profile == "quality" else "0.6B")
            else:
                fn(args.models)


if __name__ == "__main__":
    main()
