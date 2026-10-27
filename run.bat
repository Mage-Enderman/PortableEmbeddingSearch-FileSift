@echo off
setlocal
cd /d "%~dp0"
title FileSift - Portable Embedding Search

if not exist ".venv\Scripts\python.exe" (
    echo [FileSift] Virtual environment not found. Running setup first...
    call setup.bat
    if errorlevel 1 (
        echo [FileSift] Setup failed. Please check your Python or uv installation.
        pause
        exit /b 1
    )
)

echo [FileSift] Starting FileSift Desktop Application...
".venv\Scripts\python.exe" desktop.py
pause
