"""Prepare an integrity-checked wheel folder from pip's resolution report."""
import concurrent.futures
import json
from pathlib import Path
from urllib.parse import urlsplit, unquote

from provision import download

root = Path(__file__).resolve().parent.parent
report = json.loads((root / "artifacts/dependencies.json").read_text(encoding="utf-8"))
wheels = root / "artifacts/wheels"
wheels.mkdir(parents=True, exist_ok=True)


def fetch(item):
    info = item["download_info"]
    name = unquote(urlsplit(info["url"]).path.rsplit("/", 1)[1])
    download(info["url"], wheels / name, info["archive_info"]["hashes"]["sha256"])


def main():
    pending = list(report["install"])
    for attempt in range(3):
        failed = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(fetch, item): item for item in pending}
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    item = futures[future]
                    failed.append(item)
                    print("Retry needed:", item["metadata"]["name"], str(exc)[:160], flush=True)
        pending = failed
        if not pending:
            break
    if pending:
        raise RuntimeError("Some wheels could not be downloaded. Rerun to resume.")
    print("Standard wheels ready", flush=True)
    download("https://github.com/abetlen/llama-cpp-python/releases/download/v0.3.36/llama_cpp_python-0.3.36-py3-none-win_amd64.whl", wheels / "llama_cpp_python-0.3.36-py3-none-win_amd64.whl")


if __name__ == "__main__":
    main()
