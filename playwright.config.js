// Store/playwright.config.js
// @ai-rules:
// 1. [Constraint]: CI installs Chromium only -- do NOT add Firefox/WebKit projects.
// 2. [Pattern]: testDir points to tests/ where all .spec.js files live.
// 3. [Gotcha]: Self-contained tests mock routes inline. Server-dependent tests need a running app.

const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  testIgnore: ['**/post-deploy/**'],
  timeout: 30_000,
  retries: 0,
  use: {
    headless: true,
    ignoreHTTPSErrors: true,
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
});
