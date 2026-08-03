@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating TLBS virtual environment...
    py -3 -m venv .venv
    if errorlevel 1 goto :failed
)

echo Installing or updating required packages...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-tlbs.txt
if errorlevel 1 goto :failed

echo Starting Tape Lady Business Suite...
".venv\Scripts\python.exe" -m tlbs
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo TLBS could not start.
echo Copy the full error message or send a screenshot.
pause
exit /b 1
