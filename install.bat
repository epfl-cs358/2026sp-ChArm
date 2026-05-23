@echo off
setlocal enabledelayedexpansion

echo ===================================
echo === ChArm Windows Setup Script ===
echo ===================================

:: Check for python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: python is not installed or not in PATH. Please install Python 3.
    pause
    exit /b 1
)

:: Check for node
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo Warning: node is not installed. Frontend build/run will not work without Node.js.
)

:: Check for npm
where npm >nul 2>nul
if %errorlevel% neq 0 (
    echo Warning: npm is not installed. Frontend dependencies cannot be installed.
)

:: Create virtual environment if it doesn't exist
if not exist "venv" (
    echo Creating Python virtual environment in 'venv'...
    python -m venv venv
) else (
    echo Virtual environment 'venv' already exists.
)

:: Install requirements
echo Upgrading pip and installing requirements...
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt

:: Run the python setup wizard
echo Starting interactive setup wizard...
venv\Scripts\python.exe setup_wizard.py

pause
