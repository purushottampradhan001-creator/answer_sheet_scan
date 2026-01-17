# Setup Guide

## Prerequisites

### 1. Python 3.9 or Higher

**Windows:**
- Download from [python.org](https://www.python.org/downloads/)
- During installation, check "Add Python to PATH"

**macOS:**
```bash
brew install python3
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install python3 python3-pip
```

### 2. Node.js 16.x or Higher

**Windows/macOS:**
- Download from [nodejs.org](https://nodejs.org/)

**Linux:**
```bash
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs
```

## Installation Steps

### Step 1: Install Python Dependencies

```bash
cd python
pip install -r requirements.txt
```

**Note:** On some systems, use `pip3` instead of `pip`:
```bash
pip3 install -r requirements.txt
```

### Step 2: Install Electron Dependencies

```bash
cd electron
npm install
```

**Note:** If you encounter permission errors, you may need to use `sudo` on Linux/macOS (not recommended) or fix npm permissions.

## Running the Application

### Option 1: Using Startup Scripts

**Windows:**
```bash
start.bat
```

**macOS/Linux:**
```bash
./start.sh
```

### Option 2: Manual Start

**Terminal 1 - Start Python Backend:**
```bash
cd python
python image_engine.py
```

**Terminal 2 - Start Electron App:**
```bash
cd electron
npm start
```

## Building for Production

### Windows Executable

1. **Install PyInstaller** (for bundling Python):
```bash
pip install pyinstaller
```

2. **Build Python Executable:**
```bash
cd python
pyinstaller --onefile --name image_engine image_engine.py
```

3. **Build Electron App:**
```bash
cd electron
npm run build:win
```

The installer will be in `electron/dist/` folder.

### macOS Application

```bash
cd electron
npm run build:mac
```

### Linux Application

```bash
cd electron
npm run build:linux
```

## Troubleshooting

### Python Backend Won't Start

**Issue:** `ModuleNotFoundError` or import errors

**Solution:**
```bash
cd python
pip install -r requirements.txt
```

**Issue:** Port 5000 already in use

**Solution:** 
- Close other applications using port 5000
- Or modify `image_engine.py` to use a different port

### Electron App Can't Connect

**Issue:** "Cannot connect to backend"

**Solutions:**
1. Ensure Python backend is running
2. Check firewall settings
3. Verify Python backend is listening on `127.0.0.1:5000`

### Image Upload Fails

**Issue:** File dialog doesn't work

**Solution:**
- Ensure you're using the latest version of Electron
- Check file permissions
- Try using the file input fallback

**Issue:** Images not displaying

**Solution:**
- Check image format (JPG, PNG, BMP, TIFF supported)
- Verify image files are not corrupted
- Check file path permissions

## Development Mode

To enable development mode with DevTools:

**Windows:**
```bash
set NODE_ENV=development
cd electron
npm start
```

**macOS/Linux:**
```bash
export NODE_ENV=development
cd electron
npm start
```

## Testing

### Test Image Validation

1. Start the application
2. Click "New Answer Copy"
3. Upload an image
4. Try uploading the same image again (should detect duplicate)
5. Upload a very small/blurry image (should show quality warning)

### Test PDF Generation

1. Start new answer copy
2. Upload 2-3 images
3. Click "Complete & Generate PDF"
4. Check `output/` folder for generated PDF

## Project Structure

```
answersheetscanning/
├── electron/              # Electron frontend
│   ├── main.js           # Main process
│   ├── renderer.js       # Renderer process
│   ├── preload.js        # Preload script
│   ├── index.html        # UI
│   ├── styles.css        # Styling
│   └── package.json      # Electron config
├── python/               # Python backend
│   ├── image_engine.py   # Flask server
│   ├── validator.py      # Image validation
│   ├── pdf_generator.py  # PDF creation
│   └── requirements.txt  # Python dependencies
├── working/              # Temporary image storage
├── output/               # Generated PDFs
├── db/                   # SQLite database
├── start.sh              # Startup script (macOS/Linux)
├── start.bat             # Startup script (Windows)
└── README.md             # Main documentation
```

## Next Steps

1. Customize UI colors/styles in `electron/styles.css`
2. Adjust validation thresholds in `python/validator.py`
3. Modify PDF settings in `python/pdf_generator.py`
4. Add additional features as needed

## Support

For issues or questions:
1. Check the README.md
2. Review error messages in console
3. Check Python backend logs
4. Verify all dependencies are installed
