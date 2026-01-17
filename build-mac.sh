#!/bin/bash
# Build script for macOS executable
# This script builds both Python backend and Electron app for macOS

set -e  # Exit on error

echo "========================================"
echo "Building Answer Sheet Scanner for macOS"
echo "========================================"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed"
    echo "Please install Python 3.9+ using Homebrew: brew install python3"
    exit 1
fi

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "ERROR: Node.js is not installed"
    echo "Please install Node.js 16+ using Homebrew: brew install node"
    exit 1
fi

# Activate virtual environment if it exists
VENV_PATH="python/image_scanning"
if [ -d "$VENV_PATH" ] && [ -f "$VENV_PATH/bin/activate" ]; then
    echo "Activating virtual environment..."
    source "$VENV_PATH/bin/activate"
    PYTHON_CMD="python"
    PIP_CMD="pip"
else
    echo "No virtual environment found, using system Python..."
    PYTHON_CMD="python3"
    PIP_CMD="python3 -m pip"
    
    # Check if PyInstaller is installed
    if ! $PYTHON_CMD -c "import PyInstaller" &> /dev/null; then
        echo "PyInstaller not found. Installing..."
        $PIP_CMD install pyinstaller
        if [ $? -ne 0 ]; then
            echo "ERROR: Failed to install PyInstaller"
            exit 1
        fi
    fi
fi

# Install Python dependencies (skip if already installed)
echo ""
echo "[1/4] Checking Python dependencies..."
cd python
# Check if all required packages are installed
if $PYTHON_CMD -c "import flask, cv2, PIL, numpy, imagehash, reportlab, watchdog" &> /dev/null; then
    echo "All Python dependencies are already installed. Skipping installation."
else
    echo "Installing missing Python dependencies..."
    $PIP_CMD install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "WARNING: Failed to install Python dependencies, but continuing..."
        echo "If build fails, please install manually: cd python && $PIP_CMD install -r requirements.txt"
    fi
fi
cd ..

# Build Python executable
echo ""
echo "[2/4] Building Python backend executable..."
cd python
$PYTHON_CMD -m PyInstaller build_python.spec --clean --noconfirm
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to build Python executable"
    exit 1
fi
cd ..

# Install Electron dependencies
echo ""
echo "[3/4] Installing Electron dependencies..."
cd electron
npm install
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install Electron dependencies"
    exit 1
fi
cd ..

# Build Electron app
echo ""
echo "[4/4] Building Electron app for macOS..."
cd electron
npm run build:mac
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to build Electron app"
    exit 1
fi
cd ..

echo ""
echo "========================================"
echo "Build completed successfully!"
echo "========================================"
echo ""
echo "The macOS DMG can be found in: dist/"
echo ""
