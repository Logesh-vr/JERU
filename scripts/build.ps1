param([switch]$Installer, [switch]$IncludeModels)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$env:HF_HUB_DISABLE_XET = '1'
$env:HF_HOME = Join-Path $projectRoot '.jeru-data\model-cache'
# Do not let unrelated tools (e.g. Poppler's ICU DLL) enter the dependency
# search path and shadow Windows' ICU, which Qt uses on this platform.
$env:PATH = (Join-Path $projectRoot '.venv\Scripts') + ';' + (Join-Path $env:WINDIR 'System32') + ';' + $env:WINDIR + ';' + (Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0')
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run scripts\setup.ps1 first.' }
& $pythonPath -m PyInstaller --clean --noconfirm --onedir --windowed --name Jeru --icon assets\jeru.ico --log-level WARN `
  --collect-all sherpa_onnx --collect-all sherpa_onnx_core `
  --collect-all ctranslate2 --collect-all faster_whisper --collect-all llama_cpp `
  --collect-all sounddevice --collect-all _sounddevice_data --copy-metadata faster-whisper --copy-metadata PySide6-Essentials `
  --hidden-import win32com.client --hidden-import win32timezone --hidden-import pythoncom `
  launch_jeru.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
Copy-Item -LiteralPath README.md -Destination dist\Jeru\README.md -Force
Copy-Item -LiteralPath THIRD_PARTY_NOTICES.md -Destination dist\Jeru\THIRD_PARTY_NOTICES.md -Force
Copy-Item -LiteralPath VALIDATION.md -Destination dist\Jeru\VALIDATION.md -Force
Copy-Item -LiteralPath JERU_PLAN.md -Destination dist\Jeru\JERU_PLAN.md -Force
if (Test-Path -LiteralPath runtimes\espeak-ng) {
  New-Item -ItemType Directory -Path dist\Jeru\runtimes -Force | Out-Null
  Copy-Item -LiteralPath runtimes\espeak-ng -Destination dist\Jeru\runtimes\espeak-ng -Recurse -Force
}
if ($IncludeModels) {
  & $pythonPath scripts\verify_models.py
  if ($LASTEXITCODE -ne 0) { throw 'Model integrity verification failed.' }
  # Models are copied separately to support portable use and offline installation.
  & $pythonPath scripts\copy_models.py
  if ($LASTEXITCODE -ne 0) { throw 'Model packaging failed.' }
}
if ($Installer) {
  $compilerPath = Join-Path $projectRoot 'runtimes\innosetup\ISCC.exe'
  if (-not (Test-Path -LiteralPath $compilerPath)) { throw 'Inno Setup compiler not found at runtimes\innosetup\ISCC.exe.' }
  & $compilerPath /Q installer\Jeru.iss
  if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
}
