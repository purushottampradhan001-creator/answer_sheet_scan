/**
 * Application constants and configuration
 */

const API_URL = 'http://127.0.0.1:5001';
const MAX_RESTART_ATTEMPTS = 3;
const HEALTH_CHECK_RETRIES = 20;
const HEALTH_CHECK_DELAY = 1500; // milliseconds

module.exports = {
  API_URL,
  MAX_RESTART_ATTEMPTS,
  HEALTH_CHECK_RETRIES,
  HEALTH_CHECK_DELAY
};
