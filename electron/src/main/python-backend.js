/**
 * Python backend process management
 */

const { spawn } = require('child_process');
const { app, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const logger = require('../utils/logger');
const { API_URL, MAX_RESTART_ATTEMPTS, HEALTH_CHECK_RETRIES, HEALTH_CHECK_DELAY } = require('../config/constants');

class PythonBackend {
  constructor() {
    this.process = null;
    this.restartCount = 0;
    this.isShuttingDown = false;
    this.errorShown = false;
    this.isDev = !app.isPackaged;
    this.pythonDir = null;
    this.pythonExecutable = null;
    this.pythonScript = null;
    
    this._initializePaths();
  }

  _initializePaths() {
    if (this.isDev) {
      // Development mode: use system Python
      this.pythonDir = path.join(__dirname, '..', '..', '..', 'python');
      // Use new structure - run as module to handle imports correctly
      this.pythonScript = path.join(this.pythonDir, 'src', 'app', 'main.py');
      this.pythonExecutable = process.platform === 'win32' ? 'python' : 'python3';
    } else {
      // Production mode: use bundled Python executable
      const resourcesPath = process.resourcesPath;
      this.pythonDir = path.join(resourcesPath, 'python');
      
      if (process.platform === 'win32') {
        this.pythonExecutable = path.join(this.pythonDir, 'image_engine.exe');
      } else {
        this.pythonExecutable = path.join(this.pythonDir, 'image_engine');
      }
      this.pythonScript = null;
      
      // Resolve to absolute paths
      this.pythonExecutable = path.resolve(this.pythonExecutable);
      this.pythonDir = path.resolve(this.pythonDir);
      
      logger.info('Production mode paths:');
      logger.info('  Resources path:', resourcesPath);
      logger.info('  Python dir:', this.pythonDir);
      logger.info('  Python executable:', this.pythonExecutable);
    }
  }

  start() {
    // Don't start if already running
    if (this.process && !this.process.killed) {
      logger.info('Python backend is already running');
      return;
    }
    
    // Reset error tracking for new process
    this.errorShown = false;

    logger.info('Starting Python backend...');
    logger.info('Mode:', this.isDev ? 'Development' : 'Production');
    logger.info('Python executable:', this.pythonExecutable);
    logger.info('Python directory:', this.pythonDir);

    // Check if Python executable exists (for production)
    if (!this.isDev) {
      if (!fs.existsSync(this.pythonExecutable)) {
        dialog.showErrorBox(
          'Python Backend Error',
          `Python backend executable not found at:\n${this.pythonExecutable}\n\nPlease rebuild the application.`
        );
        return;
      }
      
      // Check if executable has execute permissions (macOS/Linux)
      if (process.platform !== 'win32') {
        try {
          fs.accessSync(this.pythonExecutable, fs.constants.X_OK);
        } catch (error) {
          logger.error('Python executable does not have execute permissions. Attempting to fix...');
          try {
            fs.chmodSync(this.pythonExecutable, '755');
            logger.info('Made Python executable executable');
          } catch (chmodError) {
            logger.error('Failed to set execute permissions:', chmodError);
            dialog.showErrorBox(
              'Python Backend Error',
              `Python executable does not have execute permissions.\n\nPath: ${this.pythonExecutable}\n\nPlease check file permissions.`
            );
            return;
          }
        }
      }
    }

    // Prepare command and arguments
    let command, args;
    if (this.isDev) {
      command = this.pythonExecutable;
      args = [this.pythonScript];
    } else {
      command = path.resolve(this.pythonExecutable);
      args = [];
    }

    // Use a writable working directory for production
    let workingDir = this.pythonDir;
    if (!this.isDev) {
      const userDataPath = app.getPath('userData');
      workingDir = userDataPath;
      logger.info('Using working directory:', workingDir);
    }

    // Capture stdout and stderr
    let pythonOutput = '';
    let pythonErrors = '';

    this.process = spawn(command, args, {
      cwd: workingDir,
      stdio: ['ignore', 'pipe', 'pipe'],
      shell: false,
      env: {
        ...process.env,
        PYTHONPATH: this.pythonDir
      }
    });

    // Capture stdout
    this.process.stdout.on('data', (data) => {
      const output = data.toString();
      pythonOutput += output;
      logger.info('[Python]', output.trim());
    });

    // Capture stderr
    this.process.stderr.on('data', (data) => {
      const error = data.toString();
      pythonErrors += error;
      
      const trimmed = error.trim();
      if (trimmed.includes('"GET /') || trimmed.includes('"POST /') || trimmed.includes('"PUT /') || trimmed.includes('"DELETE /')) {
        if (trimmed.includes('" 200 ') || trimmed.includes('" 201 ') || trimmed.includes('" 204 ')) {
          logger.info('[Python]', trimmed);
        } else {
          logger.warn('[Python]', trimmed);
        }
      } else {
        logger.error('[Python Error]', trimmed);
      }
    });

    this.process.on('error', (error) => {
      logger.error('Failed to start Python backend:', error);
      logger.error('Command:', command);
      logger.error('Args:', args);
      logger.error('Working dir:', workingDir);
      logger.error('Python output:', pythonOutput);
      logger.error('Python errors:', pythonErrors);
      
      const errorMessage = this.isDev
        ? `Failed to start Python backend.\n\nError: ${error.message}\n\nPlease ensure Python 3.9+ is installed and dependencies are installed (pip install -r requirements.txt)`
        : `Failed to start Python backend.\n\nError: ${error.message}\n\nExecutable: ${this.pythonExecutable}\n\nThis may indicate a corrupted installation. Please reinstall the application.`;
      
      dialog.showErrorBox('Python Backend Error', errorMessage);
    });

    this.process.on('exit', (code, signal) => {
      logger.info(`Python backend exited with code ${code}, signal ${signal}`);
      
      if (this.isShuttingDown || signal === 'SIGTERM' || signal === 'SIGINT') {
        logger.info('Python backend stopped normally');
        this.process = null;
        return;
      }
      
      if (code !== 0 && code !== null) {
        logger.error('Python output before exit:', pythonOutput);
        logger.error('Python errors before exit:', pythonErrors);
        
        if (signal !== 'SIGTERM' && signal !== 'SIGINT' && signal !== null && !this.isShuttingDown) {
          const errorMsg = `Python backend process exited unexpectedly.\n\nExit code: ${code}\nSignal: ${signal || 'none'}\n\nLast output:\n${pythonOutput.slice(-500)}\n\nLast errors:\n${pythonErrors.slice(-500)}`;
          logger.error(errorMsg);
          
          if (!this.errorShown) {
            this.errorShown = true;
            dialog.showErrorBox('Python Backend Crashed', errorMsg);
          }
        }
      }
      
      this.process = null;
    });
    
    this.process.on('spawn', () => {
      logger.info('Python backend process spawned successfully');
    });
  }

  stop() {
    if (this.process) {
      this.isShuttingDown = true;
      logger.info('Stopping Python backend...');
      try {
        this.process.kill('SIGTERM');
        
        setTimeout(() => {
          if (this.process && !this.process.killed) {
            logger.info('Force killing Python backend...');
            this.process.kill('SIGKILL');
          }
        }, 2000);
      } catch (error) {
        logger.error('Error stopping Python backend:', error);
      }
    }
  }

  async checkHealth(retries = HEALTH_CHECK_RETRIES, delay = HEALTH_CHECK_DELAY) {
    for (let i = 0; i < retries; i++) {
      try {
        const response = await fetch(API_URL + '/health');
        if (response.ok) {
          logger.info(`Python backend is ready! (after ${i + 1} attempts)`);
          return true;
        }
      } catch (error) {
        if (i < retries - 1) {
          logger.debug(`Waiting for Python backend... (${i + 1}/${retries})`);
          await new Promise(resolve => setTimeout(resolve, delay));
        } else {
          logger.error('Backend health check failed after all retries');
        }
      }
    }
    logger.warn('Python backend health check failed after all retries');
    return false;
  }

  reset() {
    this.isShuttingDown = false;
    this.errorShown = false;
    this.restartCount = 0;
  }
}

module.exports = PythonBackend;
