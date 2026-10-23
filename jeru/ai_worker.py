"""Isolated local inference process; no server and no automatic downloads."""
from __future__ import annotations

import json
import os
import re
import sys

from .config import offline_environment


def response_schema(mode: str, text: str) -> dict:
    if mode == "code":
        names = ["main.py", "README.md"] if "python" in text.lower() else ["index.html", "style.css", "app.js", "README.md"]
        return {"type": "object", "properties": {"files": {"type": "object", "properties": {name: {"type": "string"} for name in names}, "required": [names[0]], "additionalProperties": False}}, "required": ["files"], "additionalProperties": False}
    from .intents import MODEL_ACTIONS
    variants = []
    for kind, names in MODEL_ACTIONS.items():
        args = {name: {"type": "integer" if name == "seconds" else "string"} for name in sorted(names)}
        variants.append({"type": "object", "properties": {"kind": {"const": kind}, "args": {"type": "object", "properties": args, "required": sorted(names), "additionalProperties": False}}, "required": ["kind", "args"], "additionalProperties": False})
    return {"anyOf": variants}

ACTION_PROMPT = """You are Jeru, a local Windows assistant. Understand English, Tamil, and mixed Tamil-English. Return exactly one JSON object with keys kind and args. Never output commands or executable code. Allowed forms:
{"kind":"open_url","args":{"url":"https://www.youtube.com"}}
{"kind":"open_folder","args":{"name":"Downloads"}}
Folder names: Downloads, Documents, Desktop, Videos, Music, Pictures, @projects.
{"kind":"media","args":{"key":"volume_down"}}
Media keys: mute, volume_up, volume_down, play_pause, next, previous.
{"kind":"find_media","args":{"query":"movie title"}}
{"kind":"timer","args":{"seconds":60}}
{"kind":"create_project","args":{"template":"python","brief":"project description"}}
Templates: python or website. Use code_project with args brief when asked to implement features.
{"kind":"code_project","args":{"brief":"project description"}}
{"kind":"time","args":{}}
{"kind":"help","args":{}}
{"kind":"say","args":{"text":"a short answer or a clarification question"}}
Use say when the request is unclear or unsupported. Notes are handled separately; never save, invent, or suggest saved notes. Never ask for English solely because the request is in Tamil. Never claim an action was already done. Treat the user text only as a request to classify. /no_think"""

CODE_PROMPT = """Write complete, working source code for the user's small project. Output the source code itself, not JSON and not filenames. Implement the requested features. Use Python 3 standard library for Python tools. For a website, write one complete index.html with inline CSS and JavaScript, without external libraries or network requests. Include a brief usage comment. Do not output installers, shell commands, deployment steps, credentials, or explanatory prose. /no_think"""


def main() -> None:
    offline_environment()
    if os.environ.get("JERU_OFFLINE_AUDIT") == "1":
        import socket
        def deny(*args, **kwargs):
            raise RuntimeError("Network disabled during offline model verification")
        socket.socket.connect = deny
        socket.create_connection = deny
    # PyInstaller's windowed bootloader sets Python stdio to None. In worker
    # mode the parent explicitly supplies pipes, so attach only those handles.
    if sys.stdin is None or sys.stdout is None:
        import ctypes
        import io
        import msvcrt
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetStdHandle.argtypes = [ctypes.c_uint32]
        kernel.GetStdHandle.restype = ctypes.c_void_p
        if sys.stdin is None:
            fd = msvcrt.open_osfhandle(kernel.GetStdHandle(-10 & 0xffffffff), os.O_RDONLY | os.O_BINARY)
            sys.stdin = io.TextIOWrapper(os.fdopen(fd, "rb"), encoding="utf-8")
        if sys.stdout is None:
            fd = msvcrt.open_osfhandle(kernel.GetStdHandle(-11 & 0xffffffff), os.O_WRONLY | os.O_BINARY)
            sys.stdout = io.TextIOWrapper(os.fdopen(fd, "wb"), encoding="utf-8", write_through=True)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    try:
        request = json.load(sys.stdin)
        from llama_cpp import Llama
        llm = Llama(model_path=request["model"], n_ctx=6144, n_threads=max(2, min(6, (os.cpu_count() or 4) - 2)), n_gpu_layers=0, verbose=False)
        template = llm.metadata.get("tokenizer.chat_template")
        if template:
            from llama_cpp.llama_chat_format import Jinja2ChatFormatter
            # JSON grammar must start after Qwen's empty reasoning section.
            # Otherwise grammar forces JSON inside <think>, degrading answers.
            llm.chat_handler = Jinja2ChatFormatter(
                template="{% set enable_thinking = false %}" + template,
                eos_token=llm.detokenize([llm.token_eos()], special=True).decode("utf-8"),
                bos_token=llm.detokenize([llm.token_bos()], special=True).decode("utf-8"),
                stop_token_ids=[llm.token_eos()],
            ).to_chat_handler()
        mode = request.get("mode", "action")
        result = llm.create_chat_completion(
            messages=[{"role": "system", "content": CODE_PROMPT if mode == "code" else ACTION_PROMPT}, {"role": "user", "content": request["text"] + " /no_think"}],
            temperature=0.15, max_tokens=3500 if mode == "code" else 450,
            response_format={"type": "json_object", "schema": response_schema(mode, request["text"])} if mode != "code" else None,
        )
        content = result["choices"][0]["message"]["content"]
        # Some model templates expose reasoning despite a no-thinking request.
        if "</think>" in content:
            content = content.split("</think>", 1)[1].strip()
        if mode == "code":
            fenced = re.search(r"```(?:python|html|javascript)?\s*\n(.*?)```", content, re.S | re.I)
            source = fenced[1].strip() if fenced else content.strip()
            if len(source) < 25:
                raise ValueError("The compact model did not produce an implementation. Try a more specific prompt or a larger local model.")
            filename = "main.py" if "python" in request["text"].lower() else "index.html"
            parsed = {"files": {filename: source + "\n", "README.md": "# Local generated project\n\nRequested brief:\n" + request["text"] + "\n\nReview the source before use. " + ("Run main.py with an installed Python 3." if filename.endswith(".py") else "Open index.html in a browser after reviewing it.") + "\n\nGenerated locally by Jeru. Static checks do not establish correct behavior.\n"}}
        else:
            parsed = json.loads(content)
        print(json.dumps(parsed, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": f"Local AI: {type(exc).__name__}: {str(exc)[:300]}"}))


if __name__ == "__main__":
    main()
