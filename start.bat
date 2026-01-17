@echo off
REM Startup script for Windows development

echo Starting Answer Sheet Scanner Application...
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed
    pause
    exit /b 1
)

REM Check Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo Error: Node.js is not installed
    pause
    exit /b 1
)

REM Start Python backend
echo Starting Python backend...
start "Python Backend" cmd /k "cd python && python image_engine.py"

REM Wait a bit for Python to start
timeout /t 3 /nobreak >nul

REM Start Electron app
echo Starting Electron app...
cd electron
call npm start
