# Build Guide - Creating Executables for Windows and macOS

This guide explains how to create standalone executables for Windows (.exe installer) and macOS (.dmg) from your Answer Sheet Scanner application.

## Prerequisites

### For Windows Build:
- **Windows 10/11** (64-bit)
- **Python 3.9+** installed and in PATH
- **Node.js 16+** installed and in PATH
- **Visual Studio Build Tools** (for native modules, if needed)

### For macOS Build:
- **macOS 10.15+** (Catalina or later)
- **Python 3.9+** installed (via Homebrew: `brew install python3`)
- **Node.js 16+** installed (via Homebrew: `brew install node`)
- **Xcode Command Line Tools** (`xcode-select --install`)

## Quick Start

### Windows:
```bash
# Run the build script
build-windows.bat
```

### macOS:
```bash
# Make script executable (first time only)
chmod +x build-mac.sh

# Run the build script
./build-mac.sh
```

The built installer/DMG will be in the `dist/` folder.

## Manual Build Process

If you prefer to build manually, follow these steps:

### Step 1: Install Python Dependencies

```bash
cd python
pip install -r requirements.txt
pip install pyinstaller  # Required for bundling Python
```

### Step 2: Build Python Backend Executable

```bash
cd python
pyinstaller build_python.spec --clean --noconfirm
```

This creates a standalone Python executable in `python/dist/`:
- Windows: `image_engine.exe`
- macOS/Linux: `image_engine`

### Step 3: Install Electron Dependencies

```bash
cd electron
npm install
```

### Step 4: Build Electron App

**For Windows:**
```bash
npm run build:win
```

**For macOS:**
```bash
npm run build:mac
```

**For both platforms:**
```bash
npm run build:all
```

## Build Output

After a successful build, you'll find:

### Windows:
- **Installer**: `dist/Answer Sheet Scanner-1.0.0-Setup.exe`
- **Portable**: `dist/win-unpacked/` (folder with all files)

### macOS:
- **DMG**: `dist/Answer Sheet Scanner-1.0.0.dmg`
- **App Bundle**: `dist/mac/Answer Sheet Scanner.app`

## How It Works

1. **Python Backend Bundling**: PyInstaller packages the Python Flask server and all dependencies into a single executable
2. **Electron Packaging**: Electron Builder packages the Electron app and includes the Python executable as a resource
3. **Runtime**: The packaged app automatically detects and uses the bundled Python executable

## Configuration Files

### `python/build_python.spec`
PyInstaller configuration file that defines:
- Which Python files to bundle
- Hidden imports (Flask, OpenCV, etc.)
- Data files (OpenCV models, ReportLab fonts, etc.)
- Output executable name

### `electron/package.json` (build section)
Electron Builder configuration that defines:
- App metadata (name, version, ID)
- Build targets (NSIS for Windows, DMG for macOS)
- Resource bundling (Python executable location)
- Installer options

### `electron/main.js`
Updated to automatically detect:
- **Development mode**: Uses system Python
- **Production mode**: Uses bundled Python executable

## Troubleshooting

### Python Build Fails

**Error: "PyInstaller not found"**
```bash
pip install pyinstaller
```

**Error: "Module not found" during runtime**
- Add the missing module to `hiddenimports` in `build_python.spec`
- Rebuild: `pyinstaller build_python.spec --clean`

**Error: "OpenCV data files not found"**
- PyInstaller should auto-detect these, but if not:
- Check `datas` section in `build_python.spec`

### Electron Build Fails

**Error: "Python executable not found"**
- Ensure Step 2 completed successfully
- Check that `python/dist/image_engine.exe` (Windows) or `python/dist/image_engine` (macOS) exists

**Error: "Icon file not found"**
- Create `electron/icon.ico` for Windows
- Create `electron/icon.icns` for macOS
- Or remove icon references from `package.json` build config

**Error: "Code signing failed" (macOS)**
- For distribution, you need an Apple Developer certificate
- For testing, you can disable code signing in `package.json`:
  ```json
  "mac": {
    "identity": null
  }
  ```

### Runtime Issues

**App starts but Python backend doesn't work**
- Check console output for errors
- Verify Python executable is in `resources/python/` folder
- Check file permissions (macOS/Linux)

**"Port 5001 already in use"**
- Another instance might be running
- Change port in `python/image_engine.py` if needed

## Advanced Configuration

### Custom Icon

1. Create icon files:
   - Windows: `electron/icon.ico` (256x256 or larger)
   - macOS: `electron/icon.icns` (use `iconutil` to create from PNG)

2. Icons are automatically included in the build

### Custom Installer Options

Edit `electron/package.json` → `build.nsis` (Windows) or `build.dmg` (macOS) sections.

### Reduce Bundle Size

1. **Exclude unnecessary files** in `package.json`:
   ```json
   "files": [
     "**/*",
     "!node_modules/**/*",
     "!**/*.map",
     "!**/test/**/*"
   ]
   ```

2. **Optimize Python bundle**:
   - Remove unused imports
   - Use `--exclude-module` in PyInstaller

## Distribution

### Windows
- The `.exe` installer can be distributed directly
- Users can install it like any Windows application
- No additional dependencies required

### macOS
- The `.dmg` file can be distributed
- Users may need to allow the app in System Preferences → Security
- For App Store distribution, additional code signing is required

## File Structure After Build

```
dist/
├── Answer Sheet Scanner-1.0.0-Setup.exe  (Windows installer)
├── win-unpacked/                         (Windows portable)
│   └── Answer Sheet Scanner.exe
└── mac/
    └── Answer Sheet Scanner.app/        (macOS app bundle)
        └── Contents/
            └── Resources/
                └── python/               (Bundled Python executable)
                    └── image_engine
```

## Notes

- **First build takes longer** (10-20 minutes) as it downloads dependencies
- **Subsequent builds are faster** (2-5 minutes)
- **Build size**: ~200-500 MB (includes Python, Electron, and all dependencies)
- **Test the built app** before distribution to ensure everything works

## Support

If you encounter issues:
1. Check the error messages carefully
2. Verify all prerequisites are installed
3. Try cleaning and rebuilding:
   ```bash
   # Clean Python build
   rm -rf python/dist python/build python/__pycache__
   
   # Clean Electron build
   rm -rf electron/node_modules electron/dist
   rm -rf dist
   
   # Rebuild
   ./build-mac.sh  # or build-windows.bat
   ```
