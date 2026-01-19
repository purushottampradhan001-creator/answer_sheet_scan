/**
 * Window management for Electron app
 */

const { BrowserWindow } = require('electron');
const path = require('path');
const logger = require('../utils/logger');

class WindowManager {
  constructor() {
    this.mainWindow = null;
  }

  create() {
    if (this.mainWindow) {
      return this.mainWindow;
    }

    this.mainWindow = new BrowserWindow({
      width: 1200,
      height: 800,
      webPreferences: {
        nodeIntegration: false,
        contextIsolation: true,
        preload: path.join(__dirname, '..', 'preload', 'preload.js')
      },
      icon: path.join(__dirname, '..', '..', 'assets', 'icon.png')
    });

    this.mainWindow.loadFile(path.join(__dirname, '..', '..', 'index.html'));

    // Open DevTools in development
    if (process.env.NODE_ENV === 'development') {
      this.mainWindow.webContents.openDevTools();
    }

    this.mainWindow.on('closed', () => {
      this.mainWindow = null;
    });

    logger.info('Main window created');
    return this.mainWindow;
  }

  getWindow() {
    return this.mainWindow;
  }

  close() {
    if (this.mainWindow) {
      this.mainWindow.close();
    }
  }
}

module.exports = WindowManager;
