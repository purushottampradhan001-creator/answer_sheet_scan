/**
 * IPC handlers for Electron main process
 */

const { dialog, shell } = require('electron');
const fs = require('fs');
const path = require('path');
const logger = require('../utils/logger');
const { API_URL } = require('../config/constants');

function setupIpcHandlers(ipcMain, mainWindow) {
  // File selection handlers
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

  ipcMain.handle('select-folder', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ['openDirectory']
    });

    if (!result.canceled && result.filePaths.length > 0) {
      return result.filePaths[0];
    }
    return null;
  });

  // API URL handler
  ipcMain.handle('get-api-url', () => {
    return API_URL;
  });

  // File operations
  ipcMain.handle('read-file', async (event, filePath) => {
    try {
      const fileBuffer = fs.readFileSync(filePath);
      return {
        success: true,
        data: fileBuffer,
        filename: path.basename(filePath)
      };
    } catch (error) {
      logger.error('Error reading file:', error);
      return {
        success: false,
        error: error.message
      };
    }
  });

  ipcMain.handle('open-pdf', async (event, pdfPath) => {
    try {
      await shell.openPath(pdfPath);
      return { success: true };
    } catch (error) {
      logger.error('Error opening PDF:', error);
      return { success: false, error: error.message };
    }
  });

  logger.info('IPC handlers registered');
}

module.exports = { setupIpcHandlers };
