// tests/post-deploy/smoke.spec.js
// Post-deploy live smoke tests for Darwin Store.
//
// Run inside the OpenShift cluster via a Helm PostSync K8s Job.
// Also runnable locally with: STORE_URL=https://... npx playwright test tests/post-deploy/smoke.spec.js
//
// Environment variables:
//   STORE_URL   — frontend URL  (default: http://darwin-store-frontend:8080)
//   BACKEND_URL — backend API   (default: http://darwin-store-backend:8080)
//   CHAOS_URL   — chaos ctrl    (default: http://darwin-store-chaos:9000)

const { test, expect } = require('@playwright/test');

const STORE_URL   = process.env.STORE_URL   || 'http://darwin-store-frontend:8080';
const BACKEND_URL = process.env.BACKEND_URL || 'http://darwin-store-backend:8080';
const CHAOS_URL   = process.env.CHAOS_URL   || 'http://darwin-store-chaos:9000';

// Skip in GitHub Actions — cluster URLs are unreachable from GHA runners.
// Use GITHUB_ACTIONS (not CI) because the Playwright Docker image may set CI=1.
test.beforeEach(async ({}, testInfo) => {
  if (process.env.GITHUB_ACTIONS) testInfo.skip(true, 'Post-deploy smoke tests skipped in GitHub Actions');
});

// ── Smoke 1: Storefront loads ──────────────────────────────────────────────────

test.describe('Smoke 1 — Storefront loads and renders products', () => {

  test('store homepage loads without JS errors', async ({ page }) => {
    const jsErrors = [];
    page.on('pageerror', e => jsErrors.push(e.message));
    await page.goto(STORE_URL, { waitUntil: 'networkidle', timeout: 30000 });
    const critErrors = jsErrors.filter(e =>
      e.includes('Cannot read properties of undefined') ||
      e.includes('is not a function') ||
      e.includes('is not defined')
    );
    expect(critErrors, `JS errors on load: ${critErrors.join('; ')}`).toHaveLength(0);
  });

  test('product catalog renders at least one product card', async ({ page }) => {
    await page.goto(STORE_URL, { waitUntil: 'networkidle', timeout: 30000 });
    const cards = page.locator('.ds-product-card, .catalog-card');
    await expect(cards.first()).toBeVisible({ timeout: 20000 });
    expect(await cards.count()).toBeGreaterThan(0);
  });

  test('UI stretches to full viewport (no max-width constraint from old CSS)', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(STORE_URL, { waitUntil: 'networkidle', timeout: 30000 });
    const { scrollWidth, clientWidth } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 5);
  });

  test('page background is dark (PatternFly dark theme is active)', async ({ page }) => {
    await page.goto(STORE_URL, { waitUntil: 'networkidle', timeout: 30000 });
    const bg = await page.evaluate(() =>
      window.getComputedStyle(document.body).backgroundColor
    );
    expect(bg).not.toBe('rgb(255, 255, 255)');
    expect(bg).not.toBe('rgba(0, 0, 0, 0)');
  });
});

// ── Smoke 2: Campaign banner ───────────────────────────────────────────────────

test.describe('Smoke 2 — Campaign banner (type field fix)', () => {

  test('no uncaught errors when campaigns endpoint returns data', async ({ page }) => {
    const jsErrors = [];
    page.on('pageerror', e => jsErrors.push(e.message));
    await page.goto(STORE_URL, { waitUntil: 'networkidle', timeout: 30000 });
    const critErrors = jsErrors.filter(e => e.includes('TypeError') || e.includes('ReferenceError'));
    expect(critErrors).toHaveLength(0);
  });

  test('campaign banner renders when API returns type=banner', async ({ page }) => {
    await page.route('**/campaigns/active', r => r.fulfill({
      json: [{
        id: 'smoke-banner',
        title: 'Smoke Test Banner',
        type: 'banner',  // 'type', not 'campaign_type' (old field name bug)
        content: 'Live post-deploy smoke verification',
        image_url: null,
        link_url: null,
        coupon_code: null,
        product_id: null,
        start_date: new Date(Date.now() - 3600000).toISOString(),
        end_date:   new Date(Date.now() + 3600000).toISOString(),
        is_active: true,
        priority: 10,
        created_at: new Date().toISOString(),
      }],
    }));
    await page.goto(STORE_URL, { waitUntil: 'networkidle', timeout: 30000 });
    const banner = page.locator('.ds-campaign-banner, [class*="campaign"]');
    await expect(banner.first()).toBeVisible({ timeout: 10000 });
  });
});

// ── Smoke 3: Admin panel ───────────────────────────────────────────────────────

test.describe('Smoke 3 — Admin panel: Alerts product name + Invoices view fix', () => {

  test('admin page loads without JS errors', async ({ page }) => {
    const jsErrors = [];
    page.on('pageerror', e => jsErrors.push(e.message));
    await page.goto(`${STORE_URL}/admin`, { waitUntil: 'networkidle', timeout: 30000 });
    const critErrors = jsErrors.filter(e =>
      e.includes('Cannot read properties of undefined') || e.includes('is not a function')
    );
    expect(critErrors).toHaveLength(0);
  });

  test('Alerts tab shows non-empty product name when alerts exist', async ({ page }) => {
    await page.goto(`${STORE_URL}/admin`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForSelector('#viewTabs', { timeout: 15000 });
    await page.click('button[id^="pf-tab-alerts-"]');
    await page.waitForSelector('#alerts-table', { timeout: 10000 });

    const rows = await page.locator('#alerts-table tr').count();
    const emptyState = await page.locator('#alerts-table .ds-empty-state').count();
    if (rows > 0 && emptyState === 0) {
      const productCell = await page.locator('#alerts-table tr:first-child td:first-child').textContent();
      // Bug 1 fix: product name must not be blank
      expect(productCell?.trim()).not.toBe('');
    }
  });

  test('Invoices View button does not throw map error (Bug 2 fix)', async ({ page }) => {
    const jsErrors = [];
    page.on('pageerror', e => jsErrors.push(e.message));
    await page.goto(`${STORE_URL}/admin`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForSelector('#viewTabs', { timeout: 15000 });
    await page.click('button[id^="pf-tab-invoices-"]');
    await page.waitForSelector('#invoices-table', { timeout: 10000 });

    const viewBtn = page.locator('#invoices-table').getByRole('button', { name: 'View' });
    if (await viewBtn.count() > 0) {
      await viewBtn.first().click();
      await page.waitForTimeout(500);
      const mapErrors = jsErrors.filter(e =>
        e.includes("Cannot read properties of undefined (reading 'map')")
      );
      expect(mapErrors, 'Invoice View must not crash with undefined.map()').toHaveLength(0);
      await expect(page.locator('.pf-v6-c-modal-box')).toBeVisible({ timeout: 5000 });
    }
  });
});

// ── Smoke 4: Backend API health ────────────────────────────────────────────────

test.describe('Smoke 4 — Backend API field-name correctness', () => {

  test('GET /api/products returns 200 with an array', async ({ request }) => {
    const resp = await request.get(`${BACKEND_URL}/products`);
    expect(resp.status()).toBe(200);
    expect(Array.isArray(await resp.json())).toBe(true);
  });

  test('GET /api/alerts includes product_name field (Bug 1 backend fix)', async ({ request }) => {
    const resp = await request.get(`${BACKEND_URL}/alerts?status=active`);
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(Array.isArray(body)).toBe(true);
    // Alerts with a product_id must include product_name from the JOIN
    for (const alert of body.filter(a => a.product_id)) {
      expect(typeof alert.product_name).toBe('string');
      expect(alert.product_name.length).toBeGreaterThan(0);
    }
  });

  test('GET /api/invoices uses line_items and grand_total field names (Bug 2 backend fix)', async ({ request }) => {
    const resp = await request.get(`${BACKEND_URL}/invoices`);
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(Array.isArray(body)).toBe(true);
    for (const inv of body) {
      expect(inv).toHaveProperty('line_items');
      expect(inv).toHaveProperty('grand_total');
      expect(inv).toHaveProperty('customer_snapshot');
      // Old mismatched field names must not be present
      expect(inv).not.toHaveProperty('items');
      expect(inv).not.toHaveProperty('total');
      expect(inv).not.toHaveProperty('customer_name');
    }
  });

  test('GET /api/campaigns/active uses type not campaign_type', async ({ request }) => {
    const resp = await request.get(`${BACKEND_URL}/campaigns/active`);
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(Array.isArray(body)).toBe(true);
    for (const c of body) {
      expect(c).toHaveProperty('type');
      expect(c).not.toHaveProperty('campaign_type');
    }
  });
});

// ── Smoke 5: Chaos controller test-report API ──────────────────────────────────

test.describe('Smoke 5 — Chaos controller /api/test-reports', () => {

  test('POST /api/test-reports stores a test result', async ({ request }) => {
    const payload = {
      suite:       'post-deploy/smoke',
      timestamp:   new Date().toISOString(),
      passed:      5,
      failed:      0,
      skipped:     0,
      duration_ms: 12000,
      verdict:     'PASS',
      details:     'All smoke tests passed against live deployment.',
    };
    const resp = await request.post(`${CHAOS_URL}/api/test-reports`, { data: payload });
    expect(resp.status()).toBe(201);
    const body = await resp.json();
    expect(body).toHaveProperty('id');
    expect(body.status).toBe('stored');
  });

  test('GET /api/test-reports returns list of stored reports', async ({ request }) => {
    const resp = await request.get(`${CHAOS_URL}/api/test-reports`);
    expect(resp.status()).toBe(200);
    expect(Array.isArray(await resp.json())).toBe(true);
  });

  test('GET /api/test-reports/latest returns most recent report', async ({ request }) => {
    const payload = {
      suite: 'post-deploy/smoke', timestamp: new Date().toISOString(),
      passed: 6, failed: 0, skipped: 0, duration_ms: 15000,
      verdict: 'PASS', details: 'Smoke 5 latest-report check.',
    };
    await request.post(`${CHAOS_URL}/api/test-reports`, { data: payload });

    const resp = await request.get(`${CHAOS_URL}/api/test-reports/latest`);
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body).toHaveProperty('suite');
    expect(body).toHaveProperty('passed');
    expect(body).toHaveProperty('received_at');
  });

  test('chaos controller UI has a Test Reports section', async ({ page }) => {
    await page.goto(CHAOS_URL, { waitUntil: 'networkidle', timeout: 15000 });
    // Developer adds a panel with id="test-reports-panel" or text "Test Reports"
    const reportSection = page.locator('#test-reports-panel')
      .or(page.locator('[data-section="test-reports"]'))
      .or(page.getByText('Test Reports', { exact: true }).first());
    await expect(reportSection).toBeVisible({ timeout: 5000 });
  });
});
