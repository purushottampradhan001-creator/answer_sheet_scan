/**
 * Preload script for secure IPC communication
 */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  selectImageFile: () => ipcRenderer.invoke('select-image-file'),
  selectImageFiles: () => ipcRenderer.invoke('select-image-files'),
  showSaveDialog: () => ipcRenderer.invoke('show-save-dialog'),
  getApiUrl: () => ipcRenderer.invoke('get-api-url'),
  readFile: (filePath) => ipcRenderer.invoke('read-file', filePath),
  openPDF: (pdfPath) => ipcRenderer.invoke('open-pdf', pdfPath),
  selectFolder: () => ipcRenderer.invoke('select-folder')
});
