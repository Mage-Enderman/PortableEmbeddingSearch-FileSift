@echo off
setlocal
cd /d "%~dp0"
title FileSift Setup

echo =======================================================
echo   FileSift Portable Setup (EmbeddingGemma 2)
echo =======================================================

REM 1. Check if uv is available (fastest)
where uv >nul 2>nul
if %errorlevel% equ 0 (
    echo [Setup] Found uv. Creating virtual environment...
    uv venv .venv --python 3.12
    
    where nvidia-smi >nul 2>nul
    if %errorlevel% equ 0 (
        echo [Setup] NVIDIA GPU detected! Installing PyTorch with CUDA acceleration...
        uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
    )
    
    echo [Setup] Installing remaining dependencies...
    uv pip install -r requirements.txt
    goto cleanup
)

REM 2. Fallback to standard python
where python >nul 2>nul
if %errorlevel% equ 0 (
    echo [Setup] Using system Python to create virtual environment...
    python -m venv .venv
    echo [Setup] Installing dependencies...
    .venv\Scripts\python -m pip install --upgrade pip
    
    where nvidia-smi >nul 2>nul
    if %errorlevel% equ 0 (
        echo [Setup] NVIDIA GPU detected! Installing PyTorch with CUDA acceleration...
        .venv\Scripts\python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
    )
    
    .venv\Scripts\python -m pip install -r requirements.txt
    goto cleanup
)

echo [Setup ERROR] Neither uv nor python was found in PATH!
echo Please install Python (3.11 or 3.12) or uv from https://astral.sh/uv
pause
exit /b 1

:cleanup
REM Remove ~800MB of static compile-time export libraries in PyTorch wheel not used by Python runtime
if exist ".venv\Lib\site-packages\torch\lib\*.lib" (
    echo [Setup] Pruning unused static .lib compile archives to save ~800MB...
    del /f /q ".venv\Lib\site-packages\torch\lib\*.lib" >nul 2>nul
)

:done
echo =======================================================
echo   Setup Complete! You can now launch run.bat
echo =======================================================
pause
