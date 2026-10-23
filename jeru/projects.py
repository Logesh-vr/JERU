from __future__ import annotations

import ast
import json
import re
from pathlib import Path, PurePosixPath


def safe_name(brief: str) -> str:
    name = re.split(r"\b(?:that|which|with|where|to)\b", brief, maxsplit=1)[0]
    name = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE)
    name = re.sub(r"[\s_]+", "-", name).strip("-.")[:55]
    if not name or name.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        return "new-project"
    return name


def new_project(root: Path, brief: str, template: str) -> Path:
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    stem = safe_name(brief)
    target = root / stem
    for i in range(1, 1001):
        try:
            target.mkdir()
            break
        except FileExistsError:
            target = root / f"{stem}-{i}"
    else:
        raise ValueError("Too many matching project folders")
    (target / "TASK.md").write_text(f"# Project brief\n\n{brief}\n\nCreated locally by Jeru.\n", encoding="utf-8")
    (target / ".gitignore").write_text("__pycache__/\n.venv/\nnode_modules/\n.env\n", encoding="utf-8")
    if template == "python":
        (target / "main.py").write_text('"""Local project scaffold. See TASK.md for the requested behavior."""\n\ndef main():\n    print("Project scaffold ready. Implement the brief in TASK.md.")\n\nif __name__ == "__main__":\n    main()\n', encoding="utf-8")
        instructions = "Run with an installed Python: python main.py"
    else:
        (target / "index.html").write_text('<!doctype html>\n<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>New project</title><link rel="stylesheet" href="style.css"><main><h1>Project scaffold ready</h1><p>The requested features are recorded in TASK.md.</p></main><script src="app.js"></script></html>\n', encoding="utf-8")
        (target / "style.css").write_text('body{background:#10121b;color:#edf0f8;font:18px system-ui;margin:0;padding:10vw}main{max-width:800px;margin:auto}h1{color:#b8a5ff}\n', encoding="utf-8")
        (target / "app.js").write_text('// Implement the requested features from TASK.md here.\n', encoding="utf-8")
        instructions = "Open index.html with your browser. No packages or internet are required."
    (target / "README.md").write_text(f"# {stem}\n\n{instructions}\n\nThis is a scaffold, not a completed implementation of the brief.\n", encoding="utf-8")
    return target


def validate_generated_files(obj: dict) -> dict[str, str]:
    files = obj.get("files") if isinstance(obj, dict) else None
    if not isinstance(files, dict) or not 1 <= len(files) <= 12:
        raise ValueError("The model must return 1–12 source files")
    result = {}
    size = 0
    for name, content in files.items():
        if not isinstance(name, str) or not isinstance(content, str):
            raise ValueError("Source paths and contents must be strings")
        p = PurePosixPath(name)
        if not name or p.is_absolute() or ".." in p.parts or "\\" in name or ":" in name or any(x.startswith(".") for x in p.parts):
            raise ValueError(f"Unsafe generated path: {name}")
        if p.suffix.lower() not in {".py", ".html", ".css", ".js", ".json", ".md", ".txt"}:
            raise ValueError(f"Unsupported source type: {name}")
        if any(x.upper().split(".")[0] in {"CON", "NUL", "PRN", "AUX", *(f"COM{i}" for i in range(1,10)), *(f"LPT{i}" for i in range(1,10))} for x in p.parts):
            raise ValueError("Reserved Windows filename")
        if name.endswith((" ", ".")) or any(x.endswith((" ", ".")) for x in p.parts):
            raise ValueError("Ambiguous Windows filename")
        size += len(content.encode("utf-8"))
        if size > 150_000:
            raise ValueError("Generated project is too large")
        result[name] = content
    if len({name.casefold() for name in result}) != len(result):
        raise ValueError("Duplicate Windows source paths")
    return result


def write_generated(project: Path, files: dict[str, str]) -> list[str]:
    # Generated files are saved to a separate proposal. They are never executed.
    proposal = project / "generated-proposal"
    proposal.mkdir(exist_ok=False)
    problems = []
    for name, content in validate_generated_files({"files": files}).items():
        target = proposal / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        if target.suffix == ".py":
            try:
                parsed = ast.parse(content, filename=name)
                if not parsed.body or all(isinstance(node, ast.Expr) and isinstance(node.value, (ast.Name, ast.Attribute, ast.Constant)) for node in parsed.body):
                    problems.append(f"{name}: no executable implementation was generated")
            except SyntaxError as exc:
                problems.append(f"{name}:{exc.lineno}: {exc.msg}")
        elif target.suffix == ".json":
            try:
                json.loads(content)
            except ValueError as exc:
                problems.append(f"{name}: {exc}")
    (project / "GENERATION_REPORT.md").write_text("# Local generation report\n\nGenerated source is in generated-proposal/. It has not been executed.\n\n" + ("Static issues:\n" + "\n".join(problems) if problems else "Python/JSON syntax checks passed where applicable. This does not establish correct behavior."), encoding="utf-8")
    return problems
