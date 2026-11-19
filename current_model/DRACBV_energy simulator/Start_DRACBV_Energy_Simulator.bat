@echo off
title DRACBV Energy Simulator
cd /d "%~dp0"

set "PYTHON_EXE="
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else if exist "..\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=..\.venv\Scripts\python.exe"
)

echo ====================================================================
echo   DRACBV Energy Simulator (Standalone Combined System Workbench)
echo ====================================================================
echo.

if defined PYTHON_EXE (
    echo Using virtual environment: %PYTHON_EXE%
    "%PYTHON_EXE%" -m streamlit run app.py
    goto :done
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo Using system Python from PATH...
    python -m streamlit run app.py
    goto :done
)

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo Using Python Launcher py -3...
    py -3 -m streamlit run app.py
    goto :done
)

echo ERROR: Python 3.10+ was not found on this machine.
echo Please install Python or create a .venv and install requirements.txt.

:done
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Application exited with error code %ERRORLEVEL%.
    pause
)
