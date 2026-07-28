@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo TapeLadySuite8 is not installed in this folder.
  echo Run INSTALL_TAPELADYSUITE8.bat instead.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "src\app.py"
if errorlevel 1 pause
