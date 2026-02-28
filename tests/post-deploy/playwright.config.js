// tests/post-deploy/playwright.config.js
// Minimal config for post-deploy smoke tests running inside the cluster.
// Uses only the APIRequestContext (no browser) for fast HTTP-level checks.

const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: '.',
  testMatch: '*.spec.js',
  timeout: 30000,
  retries: 1,
  use: {
    // No browser needed — smoke tests use request context only
    baseURL: process.env.STORE_URL || 'http://darwin-store-frontend:8080',
  },
  reporter: [['json', { outputFile: '/tmp/test-results.json' }]],
});
