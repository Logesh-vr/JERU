# Third-party components

Jeru uses local open-source components. This private development build is not a completed public redistribution audit. Preserve upstream notices and check the exact bundled artifacts before publishing a release.

| Component | Upstream | Licensing information |
| --- | --- | --- |
| Python | https://www.python.org | Python Software Foundation license |
| PySide6 / Qt | https://doc.qt.io/qtforpython-6/ | LGPLv3/GPLv3/commercial options; native libraries remain separate in the directory bundle |
| faster-whisper | https://github.com/SYSTRAN/faster-whisper | MIT; model and inference dependencies have their own notices |
| Whisper models | https://github.com/openai/whisper | MIT; converted model provenance is recorded in its manifest |
| CTranslate2 | https://github.com/OpenNMT/CTranslate2 | MIT |
| sherpa-onnx | https://github.com/k2-fsa/sherpa-onnx | Apache-2.0; check individual model terms |
| llama.cpp / llama-cpp-python | https://github.com/ggml-org/llama.cpp / https://github.com/abetlen/llama-cpp-python | MIT |
| Qwen3 | https://huggingface.co/Qwen | Model-specific license in the publisher's model card |
| eSpeak NG | https://github.com/espeak-ng/espeak-ng | GPLv3 or later; source and notices must accompany any distribution as required by that license |
| sounddevice / PortAudio | https://github.com/spatialaudio/python-sounddevice | MIT / PortAudio license |
| PyInstaller | https://pyinstaller.org | GPL with bootloader exception |
| Inno Setup | https://jrsoftware.org | Upstream license; this build is personal and noncommercial |

The Lenovo white-backlight protocol was checked against publicly available descriptions in Lenovo Legion Toolkit. Jeru's adapter is implemented independently and does not bundle Legion Toolkit binaries or change fan, power, RGB, or firmware settings.

- Modern white-light interface: https://github.com/BartoszCichecki/LenovoLegionToolkit/blob/master/LenovoLegionToolkit.Lib/Features/WhiteKeyboardBacklight/WhiteKeyboardLenovoLightingBacklightFeature.cs
- Existing Energy driver protocol: https://github.com/BartoszCichecki/LenovoLegionToolkit/blob/master/LenovoLegionToolkit.Lib/Features/WhiteKeyboardBacklight/WhiteKeyboardDriverBacklightFeature.cs
