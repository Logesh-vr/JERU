@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" -m jeru
) else (
  echo Run scripts\setup.ps1 once to install Jeru's local dependencies.
  pause
)
