@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PIP_DISABLE_PIP_VERSION_CHECK=1
if exist ".venv-podbor\Scripts\python.exe" goto install
py -3.12 -c "import sys" >nul 2>nul
if not errorlevel 1 (
  py -3.12 -m venv .venv-podbor
  goto checkenv
)
python -c "import sys; assert sys.version_info >= (3,12)" >nul 2>nul
if not errorlevel 1 (
  python -m venv .venv-podbor
  goto checkenv
)
py -3 -c "import sys; assert sys.version_info >= (3,12)" >nul 2>nul
if not errorlevel 1 (
  py -3 -m venv .venv-podbor
  goto checkenv
)
if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" (
  "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" -m venv .venv-podbor
  goto checkenv
)
echo Install Python 3.12+ from python.org and enable Add Python to PATH.
pause
exit /b 1
:checkenv
if not exist ".venv-podbor\Scripts\python.exe" (
  echo Could not create the Python environment. See README.md.
  pause
  exit /b 1
)
:install
".venv-podbor\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Dependency installation failed. Check internet access and Python version.
  pause
  exit /b 1
)
".venv-podbor\Scripts\python.exe" -m streamlit run app.py --server.address=127.0.0.1
if errorlevel 1 pause
