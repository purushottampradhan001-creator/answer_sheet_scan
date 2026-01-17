/**
 * Electron Main Process
 * Manages application window and Python backend process
 */

const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

let mainWindow;
let pythonProcess = null;
let pythonRestartCount = 0;
let isShuttingDown = false; // Track if we're intentionally shutting down
let pythonErrorShown = false; // Track if error was already shown
const MAX_RESTART_ATTEMPTS = 3;

// Python backend configuration
// In production (packaged app), Python is bundled in resources
// In development, use system Python
const isDev = !app.isPackaged;
const API_URL = 'http://127.0.0.1:5001';

let PYTHON_DIR, PYTHON_SCRIPT, PYTHON_EXECUTABLE;

if (isDev) {
  // Development mode: use system Python
  PYTHON_DIR = path.join(__dirname, '..', 'python');
  PYTHON_SCRIPT = path.join(PYTHON_DIR, 'image_engine.py');
  PYTHON_EXECUTABLE = process.platform === 'win32' ? 'python' : 'python3';
} else {
  // Production mode: use bundled Python executable
  const resourcesPath = process.resourcesPath;
  PYTHON_DIR = path.join(resourcesPath, 'python');
  
  if (process.platform === 'win32') {
    PYTHON_EXECUTABLE = path.join(PYTHON_DIR, 'image_engine.exe');
  } else {
    PYTHON_EXECUTABLE = path.join(PYTHON_DIR, 'image_engine');
  }
  PYTHON_SCRIPT = null; // Not needed when using executable
  
  // Resolve to absolute path
  PYTHON_EXECUTABLE = path.resolve(PYTHON_EXECUTABLE);
  PYTHON_DIR = path.resolve(PYTHON_DIR);
  
  console.log('Production mode paths:');
  console.log('  Resources path:', resourcesPath);
  console.log('  Python dir:', PYTHON_DIR);
  console.log('  Python executable:', PYTHON_EXECUTABLE);
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    },
    icon: path.join(__dirname, 'icon.png')
  });

  mainWindow.loadFile('index.html');

  // Open DevTools in development
  if (process.env.NODE_ENV === 'development') {
    mainWindow.webContents.openDevTools();
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function startPythonBackend() {
  // Don't start if already running
  if (pythonProcess && !pythonProcess.killed) {
    console.log('Python backend is already running');
    return;
  }
  
  // Reset error tracking for new process
  pythonErrorShown = false;

  console.log('Starting Python backend...');
  console.log('Mode:', isDev ? 'Development' : 'Production');
  console.log('Python executable:', PYTHON_EXECUTABLE);
  console.log('Python directory:', PYTHON_DIR);

  // Check if Python executable exists (for production)
  if (!isDev) {
    if (!fs.existsSync(PYTHON_EXECUTABLE)) {
      dialog.showErrorBox(
        'Python Backend Error',
        `Python backend executable not found at:\n${PYTHON_EXECUTABLE}\n\nPlease rebuild the application.`
      );
      return;
    }
    
    // Check if executable has execute permissions (macOS/Linux)
    if (process.platform !== 'win32') {
      try {
        fs.accessSync(PYTHON_EXECUTABLE, fs.constants.X_OK);
      } catch (error) {
        console.error('Python executable does not have execute permissions. Attempting to fix...');
        // Try to make it executable
        try {
          fs.chmodSync(PYTHON_EXECUTABLE, '755');
          console.log('Made Python executable executable');
        } catch (chmodError) {
          console.error('Failed to set execute permissions:', chmodError);
          dialog.showErrorBox(
            'Python Backend Error',
            `Python executable does not have execute permissions.\n\nPath: ${PYTHON_EXECUTABLE}\n\nPlease check file permissions.`
          );
          return;
        }
      }
    }
  }

  // Prepare command and arguments
  let command, args;
  if (isDev) {
    // Development: use system Python with script
    command = PYTHON_EXECUTABLE;
    args = [PYTHON_SCRIPT];
  } else {
    // Production: use bundled executable directly with absolute path
    command = path.resolve(PYTHON_EXECUTABLE);
    args = [];
  }

  // Use a writable working directory for production
  let workingDir = PYTHON_DIR;
  if (!isDev) {
    // In production, use user's app data directory as working directory
    const userDataPath = app.getPath('userData');
    workingDir = userDataPath;
    console.log('Using working directory:', workingDir);
  }

  // Capture stdout and stderr to see what's happening
  let pythonOutput = '';
  let pythonErrors = '';

  pythonProcess = spawn(command, args, {
    cwd: workingDir,
    stdio: ['ignore', 'pipe', 'pipe'], // Capture stdout and stderr
    shell: false,
    env: {
      ...process.env,
      // Ensure bundled Python can find its resources
      PYTHONPATH: PYTHON_DIR
    }
  });

  // Capture stdout
  pythonProcess.stdout.on('data', (data) => {
    const output = data.toString();
    pythonOutput += output;
    console.log('[Python]', output.trim());
  });

  // Capture stderr
  pythonProcess.stderr.on('data', (data) => {
    const error = data.toString();
    pythonErrors += error;
    
    // Filter out Flask's normal HTTP log messages (they're not errors)
    // Flask logs HTTP requests to stderr, but 200 responses are normal
    const trimmed = error.trim();
    if (trimmed.includes('"GET /') || trimmed.includes('"POST /') || trimmed.includes('"PUT /') || trimmed.includes('"DELETE /')) {
      // This is a Flask HTTP log message, log it as info instead of error
      if (trimmed.includes('" 200 ') || trimmed.includes('" 201 ') || trimmed.includes('" 204 ')) {
        // Success status codes - log as info
        console.log('[Python]', trimmed);
      } else {
        // Other status codes might be errors
        console.warn('[Python]', trimmed);
      }
    } else {
      // Actual error message
      console.error('[Python Error]', trimmed);
    }
  });

  pythonProcess.on('error', (error) => {
    console.error('Failed to start Python backend:', error);
    console.error('Command:', command);
    console.error('Args:', args);
    console.error('Working dir:', workingDir);
    console.error('Python output:', pythonOutput);
    console.error('Python errors:', pythonErrors);
    
    const errorMessage = isDev
      ? `Failed to start Python backend.\n\nError: ${error.message}\n\nPlease ensure Python 3.9+ is installed and dependencies are installed (pip install -r requirements.txt)`
      : `Failed to start Python backend.\n\nError: ${error.message}\n\nExecutable: ${PYTHON_EXECUTABLE}\n\nThis may indicate a corrupted installation. Please reinstall the application.`;
    
    dialog.showErrorBox('Python Backend Error', errorMessage);
  });

  pythonProcess.on('exit', (code, signal) => {
    console.log(`Python backend exited with code ${code}, signal ${signal}`);
    
    // Don't log as error if it's a normal shutdown
    if (isShuttingDown || signal === 'SIGTERM' || signal === 'SIGINT') {
      console.log('Python backend stopped normally');
      pythonProcess = null;
      return;
    }
    
    // Only log errors if it crashed unexpectedly
    if (code !== 0 && code !== null) {
      console.error('Python output before exit:', pythonOutput);
      console.error('Python errors before exit:', pythonErrors);
      
      // Only show error if it crashed unexpectedly (not during shutdown)
      if (signal !== 'SIGTERM' && signal !== 'SIGINT' && signal !== null && !isShuttingDown) {
        const errorMsg = `Python backend process exited unexpectedly.\n\nExit code: ${code}\nSignal: ${signal || 'none'}\n\nLast output:\n${pythonOutput.slice(-500)}\n\nLast errors:\n${pythonErrors.slice(-500)}`;
        console.error(errorMsg);
        
        // Don't spam error dialogs - only show once
        if (!pythonErrorShown) {
          pythonErrorShown = true;
          dialog.showErrorBox('Python Backend Crashed', errorMsg);
        }
      }
    }
    
    // Clear the process reference
    pythonProcess = null;
  });
  
  // Mark process as started
  pythonProcess.on('spawn', () => {
    console.log('Python backend process spawned successfully');
  });
}

function stopPythonBackend() {
  if (pythonProcess) {
    isShuttingDown = true; // Mark that we're intentionally shutting down
    console.log('Stopping Python backend...');
    try {
      pythonProcess.kill('SIGTERM'); // Send SIGTERM for graceful shutdown
      
      // Give it a moment to shut down gracefully, then force kill if needed
      setTimeout(() => {
        if (pythonProcess && !pythonProcess.killed) {
          console.log('Force killing Python backend...');
          pythonProcess.kill('SIGKILL');
        }
      }, 2000);
    } catch (error) {
      console.error('Error stopping Python backend:', error);
    }
    // Don't set to null here - let the exit handler do it
  }
}

// Health check function
async function checkBackendHealth(retries = 20, delay = 1000) {
  for (let i = 0; i < retries; i++) {
    try {
      const response = await fetch(API_URL + '/health');
      if (response.ok) {
        console.log(`Python backend is ready! (after ${i + 1} attempts)`);
        return true;
      }
    } catch (error) {
      // Backend not ready yet
      if (i < retries - 1) {
        console.log(`Waiting for Python backend... (${i + 1}/${retries})`);
        await new Promise(resolve => setTimeout(resolve, delay));
      } else {
        console.error('Backend health check failed after all retries');
      }
    }
  }
  console.warn('Python backend health check failed after all retries');
  return false;
}

// App event handlers
app.whenReady().then(async () => {
  // Reset state for new session
  isShuttingDown = false;
  pythonErrorShown = false;
  pythonRestartCount = 0;
  
  // Start Python backend
  startPythonBackend();
  
  // Give Python backend a moment to start before health checking
  await new Promise(resolve => setTimeout(resolve, 2000));
  
  // Wait for Python backend to be ready with health check
  const isReady = await checkBackendHealth(20, 1500); // 20 retries, 1.5 seconds apart
  
  // Create window regardless (backend might start later)
  createWindow();
  
  // If backend isn't ready, show a warning in the console
  if (!isReady) {
    console.warn('Python backend may not be ready yet. The app will retry connections.');
    // Try to restart the backend if it's not running (with limit)
    if (pythonRestartCount < MAX_RESTART_ATTEMPTS) {
      setTimeout(() => {
        if (!pythonProcess || pythonProcess.killed) {
          pythonRestartCount++;
          console.log(`Restarting Python backend... (attempt ${pythonRestartCount}/${MAX_RESTART_ATTEMPTS})`);
          startPythonBackend();
          
          // Check again after restart
          setTimeout(async () => {
            const retryReady = await checkBackendHealth(10, 1000);
            if (!retryReady) {
              console.error('Python backend failed to start after restart attempts');
            }
          }, 5000);
        }
      }, 5000);
    } else {
      console.error(`Python backend failed to start after ${MAX_RESTART_ATTEMPTS} restart attempts`);
    }
  } else {
    // Reset restart count on success
    pythonRestartCount = 0;
  }

  app.on('activate', async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      // On macOS, when app is reactivated, check if backend is running
      if (!pythonProcess || pythonProcess.killed) {
        console.log('Reactivating app - Python backend not running, starting...');
        // Reset shutdown flag
        isShuttingDown = false;
        // Start backend if not running
        startPythonBackend();
        // Wait a moment for backend to start, then create window
        setTimeout(async () => {
          createWindow();
          // Check backend health after window is created
          const isReady = await checkBackendHealth(10, 1000);
          if (!isReady) {
            console.warn('Python backend not responding after reactivation');
          }
        }, 2000);
      } else {
        // Backend process exists, check if it's actually responding
        console.log('Reactivating app - checking if Python backend is responding...');
        const isReady = await checkBackendHealth(5, 500);
        if (!isReady) {
          console.warn('Python backend process exists but not responding, restarting...');
          // Process exists but not responding, restart it
          if (pythonProcess) {
            pythonProcess.kill('SIGKILL');
            pythonProcess = null;
          }
          isShuttingDown = false;
          startPythonBackend();
          setTimeout(() => {
            createWindow();
          }, 2000);
        } else {
          createWindow();
        }
      }
    }
  });
});

app.on('window-all-closed', () => {
  // On macOS, keep app running even when all windows are closed
  if (process.platform !== 'darwin') {
    stopPythonBackend();
    app.quit();
  } else {
    // On macOS, just stop the backend but keep app running
    stopPythonBackend();
  }
});

app.on('before-quit', (event) => {
  // Stop Python backend before quitting
  stopPythonBackend();
  // Give it a moment to shut down
  setTimeout(() => {
    // If process is still running, force quit
    if (pythonProcess && !pythonProcess.killed) {
      console.log('Force quitting - Python backend still running');
      pythonProcess.kill('SIGKILL');
    }
  }, 1000);
});

// Handle app termination
app.on('will-quit', () => {
  // Final cleanup
  if (pythonProcess && !pythonProcess.killed) {
    pythonProcess.kill('SIGKILL');
  }
});

// IPC handlers
ipcMain.handle('select-image-file', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    filters: [
      { name: 'Images', extensions: ['jpg', 'jpeg', 'png', 'bmp', 'tiff'] }
    ]
  });

  if (!result.canceled && result.filePaths.length > 0) {
    return result.filePaths[0];
  }
  return null;
});

ipcMain.handle('select-image-files', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile', 'multiSelections'],
    filters: [
      { name: 'Images', extensions: ['jpg', 'jpeg', 'png', 'bmp', 'tiff'] }
    ]
  });

  if (!result.canceled && result.filePaths.length > 0) {
    return result.filePaths;
  }
  return [];
});

ipcMain.handle('show-save-dialog', async () => {
  const result = await dialog.showSaveDialog(mainWindow, {
    filters: [
      { name: 'PDF', extensions: ['pdf'] }
    ]
  });

  if (!result.canceled) {
    return result.filePath;
  }
  return null;
});

ipcMain.handle('get-api-url', () => {
  return API_URL;
});

ipcMain.handle('read-file', async (event, filePath) => {
  try {
    const fileBuffer = fs.readFileSync(filePath);
    return {
      success: true,
      data: fileBuffer,
      filename: path.basename(filePath)
    };
  } catch (error) {
    return {
      success: false,
      error: error.message
    };
  }
});

ipcMain.handle('open-pdf', async (event, pdfPath) => {
  const { shell } = require('electron');
  try {
    await shell.openPath(pdfPath);
    return { success: true };
  } catch (error) {
    return { success: false, error: error.message };
  }
});

ipcMain.handle('select-folder', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory']
  });

  if (!result.canceled && result.filePaths.length > 0) {
    return result.filePaths[0];
  }
  return null;
});
