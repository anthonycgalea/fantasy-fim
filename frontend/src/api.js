// src/api.js
import axios from 'axios';

const api = axios.create({
  // Use a relative path so the API shares protocol and host with the frontend
  baseURL: '/api',
});

/**
 * Perform a request with automatic retries.
 * @param {Function} requestFn function returning a Promise from an axios request
 * @param {Object} options configuration for retries
 * @param {number} [options.retries=Infinity] number of attempts before giving up
 * @param {number} [options.delay=1000] delay between attempts in milliseconds
 */
export async function fetchWithRetry(requestFn, options = {}) {
  const { retries = Infinity, delay = 3000 } = options;
  let attempt = 0;

  while (true) {
    try {
      return await requestFn();
    } catch (err) {
      attempt += 1;
      if (retries !== Infinity && attempt > retries) {
        throw err;
      }
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
}

export default api;
