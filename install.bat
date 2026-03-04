@echo off
chcp 65001 >nul
title FocusGuard.ai v5.0 -- Setup

echo.
echo  +================================================+
echo  ^|      FOCUSGUARD.AI v5.0 -- Setup              ^|
echo  +================================================+
echo.

python --version >nul 2>&1 || (
    echo  [ERROR] Python not found.
    echo  Get it at: https://python.org/downloads
    echo  Make sure to check "Add Python to PATH"
    pause & exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  [OK] Python %PYVER%

echo  [1/3] Upgrading pip...
python -m pip install --upgrade pip --quiet

echo  [2/3] Installing dependencies...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo  [ERROR] Dependency install failed. Run manually:
    echo    pip install -r requirements.txt
    pause & exit /b 1
)
echo  [OK] Dependencies installed.

echo  [3/3] Checking Ollama (optional)...
ollama --version >nul 2>&1
if errorlevel 1 (
    echo  [SKIP] Ollama not found. OCR+CV mode will be used.
    echo         Better accuracy: https://ollama.com  then: ollama pull moondream
) else (
    ollama list 2>nul | findstr "moondream" >nul || (
        echo  [INFO] Pulling moondream model ^(~1.8 GB^)...
        ollama pull moondream
    )
    echo  [OK] Ollama ready.
)

echo.
echo  +================================================+
echo  ^|  Setup complete!                               ^|
echo  +================================================+
echo.

echo  Choose interface language / Arayuz dilini secin:
echo  [1] English
echo  [2] Turkce
echo.
set /p LANG_CHOICE="Enter choice (1 or 2): "

set LANG_ARG=--lang en
if "%LANG_CHOICE%"=="2" set LANG_ARG=--lang tr

set /p RUN="Launch FocusGuard now? (Y/N): "
if /i "%RUN%"=="Y" start python -m focusguard %LANG_ARG%
