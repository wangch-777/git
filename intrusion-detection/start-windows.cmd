@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment missing. Please follow docs/quickstart.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\dev.py
pause
