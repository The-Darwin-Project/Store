// tests/post-deploy/smoke.spec.js
// Post-deploy smoke tests — run inside the cluster after ArgoCD sync.
// Validates that the Store frontend, backend API, and chaos controller
// are reachable and returning expected responses.

const { test, expect } = require('@playwright/test');

const STORE_URL = process.env.STORE_URL || 'http://darwin-store-frontend:8080';
const BACKEND_URL = process.env.BACKEND_URL || 'http://darwin-store-backend:8080';
const CHAOS_URL = process.env.CHAOS_URL || 'http://darwin-store-chaos:9000';

// ── Frontend smoke tests ────────────────────────────────────────────────

test.describe('Frontend', () => {
  test('homepage loads and returns HTML', async ({ request }) => {
    const resp = await request.get(STORE_URL);
    expect(resp.status()).toBe(200);
    const body = await resp.text();
    expect(body).toContain('<html');
  });

  test('static assets are served (CSS/JS)', async ({ request }) => {
    // The SPA loads index.html which references built assets
    const resp = await request.get(STORE_URL);
    const body = await resp.text();
    // Vite-built apps include script tags for the JS bundle
    expect(body).toContain('<script');
  });
});

// ── Backend API smoke tests ─────────────────────────────────────────────

test.describe('Backend API', () => {
  test('GET /health returns ok', async ({ request }) => {
    const resp = await request.get(`${BACKEND_URL}/health`);
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data.status).toBe('healthy');
  });

  test('GET /products returns array', async ({ request }) => {
    const resp = await request.get(`${BACKEND_URL}/products`);
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(Array.isArray(data)).toBe(true);
  });

  test('GET /orders returns array', async ({ request }) => {
    const resp = await request.get(`${BACKEND_URL}/orders`);
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(Array.isArray(data)).toBe(true);
  });

  test('GET /customers returns array', async ({ request }) => {
    const resp = await request.get(`${BACKEND_URL}/customers`);
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(Array.isArray(data)).toBe(true);
  });

  test('GET /alerts returns array', async ({ request }) => {
    const resp = await request.get(`${BACKEND_URL}/alerts`);
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(Array.isArray(data)).toBe(true);
  });

  test('GET /invoices returns array', async ({ request }) => {
    const resp = await request.get(`${BACKEND_URL}/invoices`);
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(Array.isArray(data)).toBe(true);
  });
});

// ── Chaos controller smoke tests ────────────────────────────────────────

test.describe('Chaos Controller', () => {
  test('GET /api/status returns chaos state', async ({ request }) => {
    const resp = await request.get(`${CHAOS_URL}/api/status`);
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data).toHaveProperty('chaos');
  });

  test('GET /api/test-reports returns array', async ({ request }) => {
    const resp = await request.get(`${CHAOS_URL}/api/test-reports`);
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(Array.isArray(data)).toBe(true);
  });

  test('chaos UI loads', async ({ request }) => {
    const resp = await request.get(CHAOS_URL);
    expect(resp.status()).toBe(200);
    const body = await resp.text();
    expect(body).toContain('Chaos Controller');
  });
});
