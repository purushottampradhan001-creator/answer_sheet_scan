/**
 * Pre-build script to bundle Python backend using PyInstaller
 * This runs before electron-builder to prepare the Python executable
 */

const { execSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const pythonDir = path.join(__dirname, '..', '..', 'python');
const distDir = path.join(pythonDir, 'dist');
const specFile = path.join(pythonDir, 'build_python.spec');

console.log('Preparing Python backend for build...');
console.log('Python directory:', pythonDir);

// Check if PyInstaller is installed
try {
  execSync('pyinstaller --version', { stdio: 'ignore' });
} catch (error) {
  console.error('ERROR: PyInstaller is not installed!');
  console.error('Please install it with: pip install pyinstaller');
  process.exit(1);
}

// Check if spec file exists
if (!fs.existsSync(specFile)) {
  console.error(`ERROR: Spec file not found at ${specFile}`);
  process.exit(1);
}

// Clean previous builds
if (fs.existsSync(distDir)) {
  console.log('Cleaning previous Python build...');
  fs.rmSync(distDir, { recursive: true, force: true });
}

// Build Python executable
console.log('Building Python executable with PyInstaller...');
try {
  execSync(`pyinstaller "${specFile}" --clean --noconfirm`, {
    cwd: pythonDir,
    stdio: 'inherit'
  });
  console.log('✓ Python backend built successfully!');
} catch (error) {
  console.error('ERROR: Failed to build Python backend');
  console.error(error.message);
  process.exit(1);
}

// Verify the executable was created
const executableName = process.platform === 'win32' ? 'image_engine.exe' : 'image_engine';
const executablePath = path.join(distDir, executableName);

if (!fs.existsSync(executablePath)) {
  console.error(`ERROR: Executable not found at ${executablePath}`);
  process.exit(1);
}

console.log(`✓ Executable created: ${executablePath}`);
console.log('Python backend is ready for Electron packaging!');
