/**
 * Simple logger utility for Electron app
 */

const isDev = process.env.NODE_ENV === 'development' || !require('electron').app.isPackaged;

function log(level, ...args) {
  const timestamp = new Date().toISOString();
  const prefix = `[${timestamp}] [${level.toUpperCase()}]`;
  console.log(prefix, ...args);
}

const logger = {
  info: (...args) => log('info', ...args),
  warn: (...args) => log('warn', ...args),
  error: (...args) => log('error', ...args),
  debug: (...args) => {
    if (isDev) {
      log('debug', ...args);
    }
  }
};

module.exports = logger;
