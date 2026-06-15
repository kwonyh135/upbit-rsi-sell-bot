@echo off
set "REPO_ROOT=%~dp0.."
set "PYTHONW=%REPO_ROOT%\.venv\Scripts\pythonw.exe"

if not exist "%PYTHONW%" (
  echo Project virtual environment was not found: "%PYTHONW%"
  exit /b 1
)

cd /d "%REPO_ROOT%"
start "" /b "%PYTHONW%" -m huntbot run-auto-5m --live
