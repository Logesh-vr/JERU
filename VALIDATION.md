# Jeru validation — 18 October 2026

This document distinguishes implemented code, automated checks, and physical-user testing. It does not certify general laptop automation or complete bilingual accuracy.

## Verified in the source build

- **88 tests passed** using the workspace virtual environment. Coverage includes English/Tamil/mixed command routing, action argument boundaries, ambiguous movie selection, preventing generated path escapes and overwrites, non-execution of generated Python, malformed settings, cancellation/confirmation boundaries, speech-language/VAD fallback decisions, and sign-in enabling wake detection without starting an unsolicited recording turn. The 0.1.1 regressions cover colloquial Tamil opening commands, keeping explicit notes/searches distinct, rejecting model-generated notes, and selecting a female English voice even when the system default is male.
- Native Qt screens rendered and were visually inspected. Installed Windows fonts are explicitly registered for offscreen previews. Tamil command submission preserves Unicode.
- The controller-to-SQLite note flow passed. A shutdown request entered confirmation state and was cancelled without issuing a shutdown.
- The controller's Listening → Transcribing transition drove the real Lenovo Energy-driver brightness **0 → 2 → 0**. Original brightness was restored. No microphone was recorded during this test.
- Five generated English audio samples were processed locally with Python networking blocked. “Jeru” and “Hey Jeru” activated their wake phrases. Three unrelated command samples did not activate them. This is a small synthetic check, not a false-alarm-rate measurement.
- English samples “Open YouTube,” “Open downloads,” and “Volume down” transcribed correctly. Source inference times were approximately 1.8–2.0 seconds for this initial synthetic check with Whisper base.
- Offline Tamil speech output generated a nonempty WAV using eSpeak NG's Tamil voice. That voice is synthetic; naturalness has not been established.
- A source runtime self-check loaded Qt, microphone-device enumeration, speech recognition, wake detection, the Tamil voice, and local AI. It reported eight input-device entries, no microphone recording, and no Python network connection attempts.
- The compact local model correctly mapped three simple English paraphrases to open_url, volume_down, and time actions, at roughly 3–4 seconds each. One mixed-language paraphrase produced an irrelevant answer. Registered bilingual rules handle common commands directly and avoid this model for those commands.
- The complete synthetic wake → recording → real transcription → controller → action-dispatch pipeline passed, with actual microphone capture and final browser launch replaced by test doubles. It also passed with a longer pause between the name and command. Source-model runtime depends on CPU contention and is slower with Whisper small; the three-second target has not been established.

## Failures and resulting boundaries

- Whisper base failed a short, synthetic eSpeak Tamil command: automatic detection selected an unrelated language; forced Tamil did not yield a usable transcript. The packaged bilingual profile uses Whisper small. Small also made errors on the synthetic Tamil samples. Tamil voice input remains experimental and needs real-voice calibration; neither language support in a model card nor typed Tamil tests establish recognition accuracy. An initial recognition hint was removed after it contaminated some short transcripts with unspoken words.
- Early constrained code generation echoed filenames. The generator now requests a complete single entry-point source file, and static checks flag a filename echo as an absent implementation.
- A later local code sample produced Python source that parsed successfully but contained a logic error found by inspection. Code generation is experimental. Proposals remain separate, are not executed automatically, and are not described as behaviorally tested merely because syntax checks pass.
- Initial network downloads were slow and intermittently reset. Setup now resumes verified byte ranges and checks publisher hashes when available. Chunk directories include source identity so different speech models sharing model.bin cannot reuse one another's chunks.

## Packaged build

An initial frozen build failed because the build environment supplied Poppler's versioned ICU library where Qt expected Windows' built-in ICU. The build now restricts its DLL search PATH and cleans the dependency analysis. A rebuilt executable passed under a minimal Windows PATH with native UI, speech and wake models, two installed English voices, the Tamil voice binary, and a correctly working local inference child process. No development Python installation was on that PATH, no microphone was recorded, and Python connection attempts were blocked during that check.

Final installer and model-pack verification results are appended after packaging. A test under a genuinely clean Windows account remains outstanding.

### Installer checks — 18 October 2026

The per-user installer completed a silent installation into a new workspace staging directory (exit 0). The installed executable then passed its runtime check under a minimal Windows PATH (exit 0): native UI, microphone-device enumeration without recording, two English voices, Tamil voice availability, Whisper small, wake detection, and local Qwen inference. The local worker correctly returned the YouTube action with Python connections blocked. Uninstallation completed with exit 0; delayed self-deletion removed the staging directory, and both 32-bit and 64-bit uninstall registry entries were absent afterward. No restart was required.

The installer includes its models and the Python runtime; end users do not need a Python installation or API keys. This confirms installation behavior on this laptop, not a separate clean Windows account. The private preview is unsigned.

The tested preview was subsequently installed for the actual Windows user at `%LOCALAPPDATA%\Programs\Jeru` and opened normally. Its window was present and responding. A second launch exited successfully and reused the existing window. No startup option was enabled, and launch did not start microphone capture. Real-voice calibration remains the next user-assisted check.

## User calibration and 0.1.1 correction

The user reported saying “YouTube open பண்ணா”: transcription appeared in Tamil, but Jeru saved a note. Inspection of the latest accidental note confirmed that it contained an invented instruction to provide the request in English. Common mixed/Tamil opening verbs and YouTube spellings now route directly, with boundaries that account for Tamil vowel signs. The model's action schema and validator no longer permit note saving; explicit registered note commands still work. Existing notes are retained.

Speech now selects an installed female English voice by its language and gender metadata and uses eSpeak's `ta+f3` female variant for Tamil. Local WAV generation and packaged checks are recorded in `artifacts/*self-check-0.1.1.json`. These checks establish voice selection and synthesis, not Tamil naturalness or real-microphone recognition accuracy.

The 0.1.1 frozen executable passed under a minimal Windows PATH: Zira's female token was selected, English and Tamil WAVs contained 5.37 and 4.11 seconds of audio, mixed YouTube phrases resolved correctly, and all local models loaded. Python network attempts were blocked and none were observed. The expanded synthesis probe initially failed with an inherited Windows output handle; explicit subprocess output pipes fixed that diagnostic launch.

## Physical-user checks still required

1. Speak Jeru at normal desk distance, then issue English, Tamil, and mixed commands using the actual selected microphone.
2. Check recognition with fan noise and media playing. Tune microphone threshold and the wake phrase against real pronunciation.
3. Observe the keyboard physically while listening; the automated test verifies the driver's reported brightness state.
4. Test chosen movie folders and media-player controls. Windows key delivery does not prove every application supports the command.
5. Disconnect internet and repeat local commands. Python-network-blocked checks do not constitute an operating-system packet capture or a physical Wi-Fi-off test.
6. Install under a clean standard-user Windows account to verify the installation independently of this development machine.

Generated evidence lives under artifacts/: source-self-check.json, controller-check.json, audio-check/results.json, and ui/*.png. Raw user audio has not been collected.
