#!/bin/bash
# Startup script for development

echo "Starting Answer Sheet Scanner Application..."
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

# Check Node.js
if ! command -v node &> /dev/null; then
    echo "Error: Node.js is not installed"
    exit 1
fi

# Start Python backend in background
echo "Starting Python backend..."
cd python
python3 image_engine.py &
PYTHON_PID=$!
cd ..

# Wait a bit for Python to start
sleep 3

# Start Electron app
echo "Starting Electron app..."
cd electron
npm start

# Cleanup on exit
trap "kill $PYTHON_PID 2>/dev/null" EXIT
