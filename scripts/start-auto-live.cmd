@echo off
set "REPO_ROOT=%~dp0.."
set "PYTHONW=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"

cd /d "%REPO_ROOT%"
start "" /b "%PYTHONW%" -m huntbot run-auto-5m --live
