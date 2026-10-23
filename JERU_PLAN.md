# Jeru — local Windows voice assistant implementation plan

Prepared 17 October 2026. Implementation approved by the user after review. Progress and verification are recorded in README.md and VALIDATION.md.

Confirmed requirements: installable native desktop app; assistant name Jeru; English, Tamil, and mixed speech; local speech recognition, reasoning, speech synthesis, and automation; no cloud AI, API keys, subscription, or required external inference service.

Added requirement: turn the laptop keyboard backlight on during command listening, then restore the previous brightness when listening ends. The Lenovo white-backlight driver adapter and listening-state wiring have been implemented and tested against reported hardware brightness.

**1. Product and operating boundary**

Jeru will live in the Windows system tray and optionally start at sign-in. While the laptop is awake, a small local listener detects its wake phrase. Jeru acknowledges, hears the instruction, performs supported actions, checks the result where possible, and speaks a short response. It also provides a small native window with microphone status, transcript, current action, Stop, and settings.

Example: “Jeru” → acknowledgement → “YouTube open pannu” → open YouTube in the Windows default browser. A single sentence such as “Jeru, open YouTube” should work too, using a short in-memory audio buffer to retain words immediately after the wake phrase.

The assistant itself must operate with internet disconnected after installation. Opening YouTube or a streaming service still needs internet in that application. Model/runtime downloads are a one-time preparation step, with a manual offline model-pack import alternative. New development dependencies also need internet unless bundled or previously cached.

The core will use bundled libraries and local child processes communicating through standard input/output or named pipes. It will not require an HTTP model server, Ollama, a web dashboard, or a hosted backend. Windows system interfaces remain necessary to operate the laptop; “no APIs” is implemented as no remote AI/service dependency and no required API server.

Voice activation works while Jeru is running and the laptop is awake. Waking a sleeping or powered-off computer is outside the ordinary desktop-app scope. Pause command execution on lock, and resume listening according to the user's setting after unlock. Jeru will not bypass Windows login or administrator consent screens.

**2. Hardware and model strategy**

Read-only inspection reported an AMD Ryzen 7 7435HS and NVIDIA GeForce RTX 3050 A Laptop GPU with approximately 4 GB VRAM. System RAM was not successfully verified. These observations guide the first benchmark; they are not a performance guarantee.

Use a compact multilingual model, short context, and partial GPU offload if needed. Benchmark Qwen3-4B in Q4_K_M as an initial candidate, alongside a smaller fallback if total memory is tight. Quantization compresses model weights; runtime memory also includes context, working buffers, and other apps. Do not assume a model fits entirely in 4 GB just because its downloaded file does.

Keep wake detection lightweight and resident. Run speech recognition on CPU initially, then test acceleration. Load the general model on demand or retain it only when enough memory is available. Do not keep separate large speech, reasoning, coding, and vision models resident together. Compare CPU-only and mixed CPU/GPU operation under normal browser/editor use.

Plan a provisional 8–15 GB storage allowance for app files, initial models, and one rollback copy, to be replaced with exact sizes after benchmarking. A complete offline coding environment can require substantially more storage for language runtimes, packages, and caches.

Qwen's official model card provides GGUF variants and local llama.cpp instructions: [Qwen3-4B-GGUF](https://huggingface.co/Qwen/Qwen3-4B-GGUF). This is a candidate to test, not a claim that it is the best available model or already validated for Tamil commands.

**3. Proposed technology stack**

| Component | Initial choice | Purpose and decision gate |
| --- | --- | --- |
| Native interface | Python + PySide6 / Qt Widgets | Tray icon, overlay, settings, Unicode Tamil display; no browser or WebView UI. |
| Audio capture | Local Windows microphone capture | Selected input device, short RAM buffer, microphone reconnect handling. |
| Wake detection | sherpa-onnx keyword spotting | Configure Jeru pronunciation variants; measure missed and false activations. |
| Speech boundaries | Local voice activity detection | Distinguish speech from silence and end commands without fixed recording lengths. |
| Speech recognition | faster-whisper, multilingual small/base candidates | Transcribe locally; compare Tamil accuracy and latency before choosing the default. |
| Interpretation | Deterministic bilingual rules, then local llama.cpp model | Fast common commands; model handles paraphrases, references, and longer requests. |
| Speech output | Installed offline Windows English voice + eSpeak NG Tamil baseline | Obtain working local speech first; evaluate better Tamil voices separately. |
| Windows control | Explicit system adapters, then Windows UI Automation | Launch apps, open files, manage windows, inspect accessible controls. |
| Local data | SQLite + configuration files | Aliases, selected folder index, routines, preferences, optional action history. |
| Packaging | PyInstaller directory bundle + Windows installer | Install without requiring the user to install Python or run a terminal. |

Qt provides native Python bindings: [Qt for Python](https://doc.qt.io/qtforpython-6/). sherpa documents customizable keyword spotting: [keyword spotting](https://k2-fsa.github.io/sherpa/onnx/kws/index.html). faster-whisper supports local CPU and GPU inference, including INT8 modes: [project documentation](https://github.com/SYSTRAN/faster-whisper). llama.cpp supplies local model inference: [project documentation](https://github.com/ggml-org/llama.cpp).

**4. English, Tamil, and mixed speech**

Use multilingual Whisper models, never the English-only `.en` variants. Whisper lists Tamil among supported languages, but language support alone does not establish accuracy for the user's accent or mixed sentences. Build a small user-specific evaluation set before adding many actions. [Whisper language definitions](https://github.com/openai/whisper/blob/main/whisper/tokenizer.py)

The evaluation set should include English commands, Tamil commands, Tamil/English mixtures, app names, personal folder names, movie titles, and coding dictation. Preserve names and file paths rather than automatically translating them. Recognize equivalent intents such as “open,” “thira,” and “open pannu” through tested aliases and model interpretation. Allow correction of a transcript and saving an alias locally.

Provide Automatic, English, and Tamil recognition settings if automatic detection is unreliable for short utterances. Keep the conversation language preference separate from transcription language. Display Tamil in Unicode and accept Tamil filenames. Low-confidence or ambiguous names trigger a short clarification instead of a guessed file operation.

eSpeak NG lists Tamil support and provides a lightweight offline speech baseline. Expect a synthetic voice; natural Tamil speech is a separate quality milestone requiring a tested local voice and redistribution review. Do not silently substitute an online voice. [Supported languages](https://github.com/espeak-ng/espeak-ng/blob/master/docs/languages.md)

**5. Listening and conversation design**

States: Paused → Waiting for wake phrase → Listening → Interpreting → Clarifying/Confirming if needed → Acting → Checking result → Speaking → Waiting.

Only keyword detection and basic audio handling run continuously. Full transcription and model processing start after activation. A short chime acknowledges activation quickly; “Yes?” is optional to reduce repeated speech. Support a configurable follow-up window for “pause it,” “open the second one,” and similar references.

Calibrate the short name “Jeru” against the user's pronunciation. Offer “Hey Jeru” as an optional phrase if the short name triggers too often; do not change the name. Include a configurable push-to-talk shortcut and tray button as fallbacks.

Avoid self-triggering from Jeru's own speaker output. Initially use turn-taking: suspend normal command recognition while speaking and retain a keyboard Stop shortcut. Add voice interruption only after a separate local interrupt path is tested against speaker echo. During long actions, keep the interface and cancellation path responsive. Cancellation stops future actions and managed processes where safe; it cannot undo an already completed external action.

**6. Everyday automation scope**

| Area | Planned commands | Result verification |
| --- | --- | --- |
| Apps and sites | Open browser, YouTube, editor, calculator, Codex, or a registered app | Confirm process/window where available; distinguish opening a URL from verifying page load. |
| Folders and files | Open Downloads, Movies, a named project, or a document | Resolve indexed path and confirm launch; ask when multiple names match. |
| Local movies | Find a title in approved folders and open the associated player | Check file existence and player launch; playback state only when the player exposes it. |
| Media | Play/pause, next, previous, mute, volume | Prefer system media controls; report unsupported players. |
| Windows | Switch, minimize, maximize, close a chosen window | Check foreground/window state; preserve app save prompts. |
| Dictation | Type spoken text into a chosen app | Explicit dictation mode, verified target window, stop phrase/hotkey. |
| Local utilities | Timers, reminders, notes, screenshots | Verify saved artifact or scheduled local task. |
| Routines | Run a named sequence such as study mode | Check each step, stop on failure, summarize partial completion. |

Use the Windows default browser through the registered URL handler. YouTube search can use a search URL with encoded query text. Selecting videos, account-specific actions, and complex website interaction need separate adapters and testing. Installed-app discovery should use known app registrations and Start menu entries rather than guess executable names.

For local movies, create a filename index only for user-selected folders. If several copies exist, ask which one. “Watch a movie” without a title should open the library or ask for a title, rather than invent a choice or location.

For extensibility, each supported action declares its name, arguments, permission level, execution method, timeout, observable result, and reversibility. Prefer direct system operations; use Windows UI Automation for accessible controls, and screen coordinates only as a tested app-specific fallback. Windows UI Automation exposes application controls programmatically: [Microsoft overview](https://learn.microsoft.com/en-us/dotnet/framework/ui-automation/ui-automation-overview).

**7. Interpretation and action reliability**

Common commands bypass the language model. Longer commands become structured proposed actions such as open_url, open_folder, set_volume, find_media, create_project, or run_routine. Validate the action name and every argument before execution. A model response or raw transcript must never become an unrestricted PowerShell command.

Track the current target app, recent file/search results, and current task for follow-ups. This context expires and can be cleared. Ask for clarification when “it” has several plausible meanings. Limit multi-step jobs to a bounded number of actions and retries; show progress and partial failures.

Treat webpage text, documents, and tool output as data. They cannot grant Jeru new permissions or authorize unrelated commands. Never claim success from a generated plan alone. The executor returns evidence such as a process/window, file, exit code, or application state. Report “opened the link” when page loading was not observable.

**8. Local coding workflow and Codex**

The strict offline default will be Jeru's own bounded coding workflow using a local model and installed development tools. Initial targets are small Python utilities and simple frontend projects from prepared templates. Broad autonomous app construction is a later experiment; a compact model on this laptop should not be promised the capability of a hosted frontier coding system.

Workflow: dictate prompt → show/read back the important requirements and project name → create a new folder under a configured projects root → write a local task brief → choose a bundled template → generate changes → show the diff → run approved checks in an appropriately isolated executor → attempt a limited number of repairs → report results and open the editor.

Preserve an existing folder instead of overwriting it. Keep checkpoints before edits. Separate model-generated changes from downloaded dependencies. Provide an offline template/package cache, and report missing packages while offline. A generated project may open in a browser, but Jeru itself remains a native desktop app.

Two Codex capabilities must be distinguished:

- Launching the installed Codex application is ordinary local app automation; it does not establish offline inference.
- Official Codex configuration documents `--oss` local providers through Ollama or LM Studio. That is an optional compatibility investigation, not the core architecture or a guaranteed desktop integration. It generally introduces a local service interface, so it is outside the strict no-server baseline. Validate actual CLI/provider/model compatibility, network behavior, and telemetry configuration before offering an offline mode. [Official configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)

Never silently switch from an unavailable local model to hosted Codex or another remote model.

**9. Permissions, execution boundaries, and privacy**

Ordinary registered actions such as opening apps and changing volume should run directly after a recognized instruction. Ambiguous targets need clarification. Deleting files, overwriting existing work, installing software, sending messages, publishing, or shutting down should present the exact intended action and obtain confirmation. Persistent preferences can streamline supported routines without granting arbitrary command execution.

Run without administrator privileges by default. Limit indexed folders and direct file-operation targets. Validate resolved paths, including links, so an allowed folder is not a route to another location. Keep ordinary automation separate from a coding executor.

A working directory and an action allowlist do not sandbox arbitrary generated code: child processes can access other user files. Before unattended execution, validate an OS-enforced isolation option supported by the installed Windows edition. Until that exists, generated code and dependency installation require a reviewable run approval; do not describe them as isolated merely because they run in a project folder.

Keep raw audio in a short RAM buffer and discard it after processing. Raw recording is off by default; any diagnostic recording is explicit. Store preferences and selected metadata locally. Make transcript/action history optional and clearable. No telemetry or cloud fallback in Jeru. Leave websites' own network behavior to the apps the user explicitly opens.

**10. Desktop installation and maintenance**

Deliver Jeru-Setup.exe, an optional portable bundle, and versioned model packs. Use a per-user installation and data under %LOCALAPPDATA%\Jeru. Installer setup checks microphone availability, lets the user choose folders, loads/imports model packs, and performs a short voice calibration. Models carry expected sizes, versions, sources, licenses, and checksums.

Bundle Python and required runtime libraries so daily use needs no terminal. Prefer a directory bundle to avoid extracting large models from a one-file executable at every launch. Keep models separate from app updates. Review dependencies and voice/model redistribution terms before distributing an installer. [PyInstaller packaging behavior](https://www.pyinstaller.org/en/stable/operating-mode.html)

Include microphone mute, startup toggle, language settings, model status, resource settings, and an action log. Handle device changes, suspend/resume, missing files, failed worker processes, and out-of-memory errors without freezing the desktop UI. Uninstall should offer to remove or preserve models and user data.

**11. Phased implementation and review gates**

| Phase | Deliverable | Gate before expanding scope |
| --- | --- | --- |
| 0. Feasibility | Verify RAM/Windows edition, benchmark wake phrase, bilingual recognition, speech output, and compact model | Record real latency, memory, Tamil/mixed command quality, and usable model selection. |
| 1. Native foundation | Tray, overlay, microphone controls, hotkey, settings, worker lifecycle | App stays responsive, pauses correctly, and recovers after microphone disconnect. |
| 2. Voice basics | Wake → acknowledge → transcribe → execute basic app/site/folder commands → reply | Real microphone tests pass in English, Tamil, and mixed speech, including Wi-Fi off. |
| 3. Everyday control | Media, windows, movie index, dictation, notes, timers, ambiguity handling | Verify real app states and partial failures; unsupported controls reported honestly. |
| 4. Natural commands | Local model, short conversation context, routines | Paraphrases map to valid actions; model failures cannot bypass validation. |
| 5. Coding prototype | Project templates, local generation, diffs, checks, checkpoints, bounded repair | One small end-to-end project is built and checked offline using cached tools; execution boundary documented. |
| 6. Installer and hardening | Setup/portable package, model import, lifecycle recovery, diagnostics | Clean standard-user installation, offline run, upgrade, and uninstall tested. |

Indicative effort, not a deadline: roughly 25–45 focused hours for the first useful bilingual assistant if speech benchmarks are acceptable; roughly 80–160 hours for the broader desktop product. Advanced unattended coding and general visual automation can extend this substantially. Revise estimates after Phase 0 rather than commit to speed before hearing the user's actual microphone recordings.

**12. Acceptance tests and measurable targets**

- After model provisioning, disconnect internet and complete wake, local app launch, folder opening, local movie playback launch, volume control, bilingual replies, and one cached-template coding task. Separately inspect Jeru-owned processes for unexpected network attempts; Wi-Fi-off success alone does not prove no attempted traffic.
- Collect 30 live commands each in English, Tamil, and mixed speech. Record transcription, interpreted intent, actual action, correction rate, and latency separately. Target at least 90% correct first-attempt action selection per group before expanding the command library; tune after the baseline.
- Test wake phrase at desk distance and normal room distance, with fan noise and speaker playback. Initial targets: at least 90% wake detection under the agreed conditions and no more than one false activation per two-hour background session. Longer use is required to establish a reliable daily rate.
- Target acknowledgement within about one second of wake detection and basic command completion within about three seconds after speech ends when warm. These are benchmark goals, not measured promises. Track cold loading and model-driven commands separately, including median and slower cases.
- Measure idle CPU/RAM, active RAM/VRAM, battery impact, and behavior while browser/editor are open. Avoid a hard resource claim until measured. If budgets fail, reduce model size, context, or residency.
- Exercise stop/cancel, duplicate commands, ambiguous filenames, missing apps, locked session, sleep/resume, microphone removal, model failure, malicious document instructions, path escapes, and confirmation boundaries.
- Test the installed app on a clean standard-user Windows environment, not just the development machine. Record which commands are verified per application and which remain experimental.

**13. Scope recommendation for the first build**

First deliver a native, offline Jeru that wakes to its name, understands English/Tamil/mixed instructions, opens the default browser and selected apps/folders, finds local movies, controls media/volume, gives short spoken responses, and stops reliably. Establish those daily-use foundations before expanding into flexible local-model planning and coding.

This plan describes the full intended scope. The current implementation is a first desktop build; general visual automation and unattended coding remain later milestones. See VALIDATION.md for implemented and verified boundaries.
