@echo off
setlocal
cd /d "%~dp0"
title FileSift - Portable Embedding Search (Browser Mode)

if not exist ".venv\Scripts\python.exe" (
    call setup.bat
)

echo [FileSift] Starting FileSift in Web Browser...
".venv\Scripts\python.exe" desktop.py --browser
pause
