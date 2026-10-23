param([ValidateSet('compact','balanced','quality')][string]$Profile = 'balanced')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
  py -3.11 -m venv .venv
  if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 is required for development setup.' }
}
& .\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt --only-binary=:all: --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
if ($LASTEXITCODE -ne 0) { throw 'Pinned desktop dependency installation failed.' }
& .\.venv\Scripts\python.exe scripts\provision.py all --profile $Profile
if ($LASTEXITCODE -ne 0) { throw 'Model setup was interrupted. Run this script again to resume.' }
Write-Output 'Models ready. Double-click Launch Jeru.cmd. Tamil output also needs the bundled eSpeak NG runtime.'
