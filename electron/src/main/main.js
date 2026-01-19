/**
 * Electron Main Process Entry Point
 * Manages application lifecycle and coordinates components
 */

const { app, BrowserWindow, ipcMain } = require('electron');
const logger = require('../utils/logger');
const WindowManager = require('./window');
const PythonBackend = require('./python-backend');
const { setupIpcHandlers } = require('../ipc/handlers');
const { MAX_RESTART_ATTEMPTS, HEALTH_CHECK_RETRIES, HEALTH_CHECK_DELAY } = require('../config/constants');

// Initialize managers
const windowManager = new WindowManager();
const pythonBackend = new PythonBackend();

// App event handlers
app.whenReady().then(async () => {
  logger.info('Application starting...');
  
  // Reset state for new session
  pythonBackend.reset();
  
  // Start Python backend
  pythonBackend.start();
  
  // Give Python backend a moment to start before health checking
  await new Promise(resolve => setTimeout(resolve, 2000));
  
  // Wait for Python backend to be ready with health check
  const isReady = await pythonBackend.checkHealth(HEALTH_CHECK_RETRIES, HEALTH_CHECK_DELAY);
  
  // Create window regardless (backend might start later)
  windowManager.create();
  
  // Setup IPC handlers
  setupIpcHandlers(ipcMain, windowManager.getWindow());
  
  // If backend isn't ready, show a warning in the console
  if (!isReady) {
    logger.warn('Python backend may not be ready yet. The app will retry connections.');
    // Try to restart the backend if it's not running (with limit)
    if (pythonBackend.restartCount < MAX_RESTART_ATTEMPTS) {
      setTimeout(() => {
        if (!pythonBackend.process || pythonBackend.process.killed) {
          pythonBackend.restartCount++;
          logger.info(`Restarting Python backend... (attempt ${pythonBackend.restartCount}/${MAX_RESTART_ATTEMPTS})`);
          pythonBackend.start();
          
          // Check again after restart
          setTimeout(async () => {
            const retryReady = await pythonBackend.checkHealth(10, 1000);
            if (!retryReady) {
              logger.error('Python backend failed to start after restart attempts');
            }
          }, 5000);
        }
      }, 5000);
    } else {
      logger.error(`Python backend failed to start after ${MAX_RESTART_ATTEMPTS} restart attempts`);
    }
  } else {
    // Reset restart count on success
    pythonBackend.restartCount = 0;
  }

  app.on('activate', async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      // On macOS, when app is reactivated, check if backend is running
      if (!pythonBackend.process || pythonBackend.process.killed) {
        logger.info('Reactivating app - Python backend not running, starting...');
        pythonBackend.reset();
        pythonBackend.start();
        setTimeout(async () => {
          windowManager.create();
          const isReady = await pythonBackend.checkHealth(10, 1000);
          if (!isReady) {
            logger.warn('Python backend not responding after reactivation');
          }
        }, 2000);
      } else {
        logger.info('Reactivating app - checking if Python backend is responding...');
        const isReady = await pythonBackend.checkHealth(5, 500);
        if (!isReady) {
          logger.warn('Python backend process exists but not responding, restarting...');
          if (pythonBackend.process) {
            pythonBackend.process.kill('SIGKILL');
            pythonBackend.process = null;
          }
          pythonBackend.reset();
          pythonBackend.start();
          setTimeout(() => {
            windowManager.create();
          }, 2000);
        } else {
          windowManager.create();
        }
      }
    }
  });
});

app.on('window-all-closed', () => {
  // On macOS, keep app running even when all windows are closed
  if (process.platform !== 'darwin') {
    pythonBackend.stop();
    app.quit();
  } else {
    // On macOS, just stop the backend but keep app running
    pythonBackend.stop();
  }
});

app.on('before-quit', (event) => {
  // Stop Python backend before quitting
  pythonBackend.stop();
  // Give it a moment to shut down
  setTimeout(() => {
    if (pythonBackend.process && !pythonBackend.process.killed) {
      logger.info('Force quitting - Python backend still running');
      pythonBackend.process.kill('SIGKILL');
    }
  }, 1000);
});

// Handle app termination
app.on('will-quit', () => {
  // Final cleanup
  if (pythonBackend.process && !pythonBackend.process.killed) {
    pythonBackend.process.kill('SIGKILL');
  }
});

logger.info('Main process initialized');
