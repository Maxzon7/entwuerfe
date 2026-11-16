@echo off
setlocal
chcp 65001 >nul
title Combined System Workbench - Streamlit Launcher

cd /d "%~dp0"

set "PY_EXE="
set "PY_ARGS="

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" -m streamlit --version >nul 2>&1
    if not errorlevel 1 (
        set "PY_EXE=%~dp0.venv\Scripts\python.exe"
    )
)

if not defined PY_EXE if exist "%~dp0..\.venv\Scripts\python.exe" (
    "%~dp0..\.venv\Scripts\python.exe" -m streamlit --version >nul 2>&1
    if not errorlevel 1 (
        set "PY_EXE=%~dp0..\.venv\Scripts\python.exe"
    )
)

if not defined PY_EXE (
    python -m streamlit --version >nul 2>&1
    if not errorlevel 1 (
        set "PY_EXE=python"
    )
)

if not defined PY_EXE (
    py -3 -m streamlit --version >nul 2>&1
    if not errorlevel 1 (
        set "PY_EXE=py"
        set "PY_ARGS=-3"
    )
)

if not defined PY_EXE (
    echo [ERROR] Python with Streamlit was not found.
    echo Please install dependencies with: pip install -r requirements.txt
    pause
    exit /b 1
)

echo Starting Combined System Workbench...
echo The browser will open automatically. Close this window to stop the server.
"%PY_EXE%" %PY_ARGS% -m streamlit run "ui_sandbox\Combined_sandbox\app.py" --server.headless false

if errorlevel 1 (
    echo.
    echo [ERROR] Streamlit exited with an error.
    pause
)
endlocal
