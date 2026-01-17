@echo off
REM Build script for Windows executable
REM This script builds both Python backend and Electron app for Windows

echo ========================================
echo Building Answer Sheet Scanner for Windows
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.9+ and add it to PATH
    pause
    exit /b 1
)

REM Check if Node.js is installed
node --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js is not installed or not in PATH
    echo Please install Node.js 16+ and add it to PATH
    pause
    exit /b 1
)

REM Check if PyInstaller is installed
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    pip install pyinstaller
    if errorlevel 1 (
        echo ERROR: Failed to install PyInstaller
        pause
        exit /b 1
    )
)

REM Install Python dependencies
echo.
echo [1/4] Installing Python dependencies...
cd python
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install Python dependencies
    pause
    exit /b 1
)
cd ..

REM Build Python executable
echo.
echo [2/4] Building Python backend executable...
cd python
python -m PyInstaller build_python.spec --clean --noconfirm
if errorlevel 1 (
    echo ERROR: Failed to build Python executable
    pause
    exit /b 1
)
cd ..

REM Install Electron dependencies
echo.
echo [3/4] Installing Electron dependencies...
cd electron
call npm install
if errorlevel 1 (
    echo ERROR: Failed to install Electron dependencies
    pause
    exit /b 1
)
cd ..

REM Build Electron app
echo.
echo [4/4] Building Electron app for Windows...
cd electron
call npm run build:win
if errorlevel 1 (
    echo ERROR: Failed to build Electron app
    pause
    exit /b 1
)
cd ..

echo.
echo ========================================
echo Build completed successfully!
echo ========================================
echo.
echo The Windows installer can be found in: dist\Answer Sheet Scanner-1.0.0-Setup.exe
echo.
pause
