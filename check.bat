@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv-podbor\Scripts\python.exe" (
  echo Run run.bat first to install dependencies.
  pause
  exit /b 1
)
set LLM_ENABLED=0
".venv-podbor\Scripts\python.exe" -m pytest -q
pause
