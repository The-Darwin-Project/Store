// tests/verify_admin_ui_evt568243ca.spec.js
// Self-contained Playwright tests for Admin UI bugs reported in evt-568243ca (Turn 92):
//
//   Bug 1 — Alerts tab: product name column was blank.
//            Root cause: /alerts did not JOIN products/suppliers tables.
//            Fix (commit deea311): added LEFT JOIN, product_name + supplier_name now in response.
//
//   Bug 2 — Invoices tab: clicking 'View' threw:
//            "TypeError: Cannot read properties of undefined (reading 'map')"
//            Root cause: frontend read invoice.items / invoice.total / invoice.customer_name
//            but backend returns line_items / grand_total / customer_snapshot.{name,email}.
//            Fix (commit deea311): aligned frontend types + InvoiceModal to use backend field names.
//
// Strategy: serve compiled React dist via route interception, mock API responses
// with the ACTUAL backend data format, and assert expected UI behaviour.
// Tests run without any live server.

const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const DIST_DIR = path.resolve(__dirname, '../frontend/dist');
const DIST_EXISTS = fs.existsSync(path.join(DIST_DIR, 'index.html'));

// ── Mock data (matches actual backend API contract after fix) ──────────────────

// Alerts: backend now JOINs products + suppliers → returns product_name, supplier_name
const MOCK_ALERTS = [
  {
    id: 'alert-1',
    type: 'restock',
    message: "Restock needed: 'Widget Alpha' stock is 5, below threshold of 10.",
    status: 'active',
    product_id: 'prod-1',
    product_name: 'Widget Alpha',
    supplier_id: 'sup-1',
    supplier_name: 'Acme Supplies',
    current_stock: 5,
    reorder_threshold: 10,
    created_at: new Date().toISOString(),
  },
  {
    id: 'alert-2',
    type: 'restock',
    message: "Restock needed: 'Gadget Beta' stock is 2, below threshold of 5.",
    status: 'active',
    product_id: 'prod-2',
    product_name: 'Gadget Beta',
    supplier_id: null,
    supplier_name: null,
    current_stock: 2,
    reorder_threshold: 5,
    created_at: new Date().toISOString(),
  },
  {
    id: 'alert-3',
    type: 'restock',
    message: "Restock needed: 'Thing Gamma' stock is 0, below threshold of 3.",
    status: 'ordered',
    product_id: 'prod-3',
    product_name: 'Thing Gamma',
    supplier_id: null,
    supplier_name: null,
    current_stock: 0,
    reorder_threshold: 3,
    created_at: new Date(Date.now() - 86400000).toISOString(),
  },
];

// Invoices: backend returns line_items, grand_total, customer_snapshot (after fix)
const MOCK_INVOICES = [
  {
    id: 'inv-1',
    invoice_number: 1001,
    order_id: 'order-aabbccdd-1111',
    customer_snapshot: {
      name: 'Alice Smith',
      email: 'alice@example.com',
    },
    line_items: [
      { product_name: 'Widget Alpha', sku: 'WA-001', unit_price: 29.99, quantity: 2, line_total: 59.98 },
      { product_name: 'Gadget Beta',  sku: 'GB-001', unit_price: 49.99, quantity: 1, line_total: 49.99 },
    ],
    subtotal: 109.97,
    coupon_code: null,
    discount_amount: 0.0,
    grand_total: 109.97,
    created_at: new Date().toISOString(),
  },
];

// ── Helpers ────────────────────────────────────────────────────────────────────

async function setupAdmin(page, { alerts = [], invoices = [] } = {}) {
  const indexHtml = fs.readFileSync(path.join(DIST_DIR, 'index.html'), 'utf8');

  await page.route('http://localhost/', r => r.fulfill({ contentType: 'text/html', body: indexHtml }));
  await page.route('http://localhost/admin', r => r.fulfill({ contentType: 'text/html', body: indexHtml }));

  await page.route('http://localhost/assets/**', async r => {
    const url = new URL(r.request().url());
    const filePath = path.join(DIST_DIR, url.pathname);
    if (fs.existsSync(filePath)) {
      const body = fs.readFileSync(filePath);
      const ext = path.extname(filePath);
      const contentType =
        ext === '.js'    ? 'application/javascript' :
        ext === '.css'   ? 'text/css' :
        ext === '.woff2' ? 'font/woff2' : 'application/octet-stream';
      return r.fulfill({ contentType, body });
    }
    return r.abort();
  });

  await page.route('**/alerts**',    r => r.fulfill({ json: alerts }));
  await page.route('**/invoices**',  r => r.fulfill({ json: invoices }));
  await page.route('**/products**',  r => r.fulfill({ json: [] }));
  await page.route('**/orders**',    r => r.fulfill({ json: [] }));
  await page.route('**/customers**', r => r.fulfill({ json: [] }));
  await page.route('**/suppliers**', r => r.fulfill({ json: [] }));
  await page.route('**/coupons**',   r => r.fulfill({ json: [] }));
  await page.route('**/campaigns**', r => r.fulfill({ json: [] }));
  await page.route('**/reviews**',   r => r.fulfill({ json: [] }));
  await page.route('**/auth**',      r => r.fulfill({ json: {} }));
  await page.route('**/dashboard**', r => r.fulfill({ json: {
    total_products: 10, total_orders: 5, active_alerts: 2, total_revenue: 499.95,
    low_stock_products: [], recent_orders: [],
  }}));

  await page.goto('http://localhost/admin', { waitUntil: 'domcontentloaded', timeout: 20000 });
}

// PF6 Tab buttons render with id: pf-tab-{eventKey}-{tabId}
// e.g. <Tab eventKey="alerts" id="alerts-tab"> → button#pf-tab-alerts-alerts-tab
async function clickAdminTab(page, eventKey) {
  await page.click(`button[id^="pf-tab-${eventKey}-"]`);
  await page.waitForTimeout(800);
}

// ── Section 1: Alerts Tab ──────────────────────────────────────────────────────

test.describe('1. Admin Alerts Tab — product name display (Bug 1 fix verification)', () => {
  test.beforeEach(({}, testInfo) => {
    if (!DIST_EXISTS) testInfo.skip(true, 'frontend/dist not built — skipping compiled-app tests');
  });

  test('alerts table renders and is visible after clicking Alerts tab', async ({ page }) => {
    await setupAdmin(page, { alerts: MOCK_ALERTS });
    await page.waitForSelector('#viewTabs', { timeout: 15000 });
    await clickAdminTab(page, 'alerts');
    await page.waitForSelector('#alerts-table', { timeout: 10000 });
    await expect(page.locator('#alerts-table')).toBeVisible();
  });

  test('product name column shows name from API response (Bug 1 fixed)', async ({ page }) => {
    await setupAdmin(page, { alerts: MOCK_ALERTS });
    await page.waitForSelector('#viewTabs', { timeout: 15000 });
    await clickAdminTab(page, 'alerts');
    await page.waitForSelector('#alerts-table', { timeout: 10000 });

    // First cell should have the product name — was blank before the backend JOIN fix
    const firstProductCell = await page.locator('#alerts-table tr:first-child td:first-child').textContent();
    expect(firstProductCell?.trim()).toBe('Widget Alpha');
  });

  test('all three alert rows show their correct product names', async ({ page }) => {
    await setupAdmin(page, { alerts: MOCK_ALERTS });
    await page.waitForSelector('#viewTabs', { timeout: 15000 });
    await clickAdminTab(page, 'alerts');
    await page.waitForSelector('#alerts-table', { timeout: 10000 });

    const productNames = await page.locator('#alerts-table tr td:first-child').allTextContents();
    expect(productNames.map(n => n.trim())).toEqual(['Widget Alpha', 'Gadget Beta', 'Thing Gamma']);
  });

  test('current stock and reorder threshold columns render correctly', async ({ page }) => {
    await setupAdmin(page, { alerts: MOCK_ALERTS });
    await page.waitForSelector('#viewTabs', { timeout: 15000 });
    await clickAdminTab(page, 'alerts');
    await page.waitForSelector('#alerts-table', { timeout: 10000 });

    const firstRow = page.locator('#alerts-table tr:first-child td');
    expect(await firstRow.nth(1).textContent()).toBe('5');   // current_stock
    expect(await firstRow.nth(2).textContent()).toBe('10');  // reorder_threshold
  });

  test('supplier column shows supplier name or dash when none', async ({ page }) => {
    await setupAdmin(page, { alerts: MOCK_ALERTS });
    await page.waitForSelector('#viewTabs', { timeout: 15000 });
    await clickAdminTab(page, 'alerts');
    await page.waitForSelector('#alerts-table', { timeout: 10000 });

    const supplierCells = await page.locator('#alerts-table tr td:nth-child(4)').allTextContents();
    expect(supplierCells[0].trim()).toBe('Acme Supplies');
    expect(supplierCells[1].trim()).toBe('-');
  });

  test('active alerts have Mark Ordered and Dismiss action buttons', async ({ page }) => {
    await setupAdmin(page, { alerts: MOCK_ALERTS });
    await page.waitForSelector('#viewTabs', { timeout: 15000 });
    await clickAdminTab(page, 'alerts');
    await page.waitForSelector('#alerts-table', { timeout: 10000 });

    const activeRow = page.locator('#alerts-table tr:first-child');
    await expect(activeRow.getByRole('button', { name: 'Mark Ordered' })).toBeVisible();
    await expect(activeRow.getByRole('button', { name: 'Dismiss' })).toBeVisible();
  });

  test('ordered-status alert has no action buttons', async ({ page }) => {
    await setupAdmin(page, { alerts: MOCK_ALERTS });
    await page.waitForSelector('#viewTabs', { timeout: 15000 });
    await clickAdminTab(page, 'alerts');
    await page.waitForSelector('#alerts-table', { timeout: 10000 });

    const orderedRow = page.locator('#alerts-table tr:nth-child(3)');
    const buttons = await orderedRow.getByRole('button').count();
    expect(buttons).toBe(0);
  });

  test('empty state shown when there are no alerts', async ({ page }) => {
    await setupAdmin(page, { alerts: [] });
    await page.waitForSelector('#viewTabs', { timeout: 15000 });
    await clickAdminTab(page, 'alerts');
    await page.waitForSelector('#alerts-table', { timeout: 10000 });

    const emptyCell = await page.locator('#alerts-table .ds-empty-state').textContent();
    expect(emptyCell?.trim()).toBe('No alerts.');
  });
});

// ── Section 2: Invoices Tab ────────────────────────────────────────────────────

test.describe('2. Admin Invoices Tab — View button without crash (Bug 2 fix verification)', () => {
  test.beforeEach(({}, testInfo) => {
    if (!DIST_EXISTS) testInfo.skip(true, 'frontend/dist not built — skipping compiled-app tests');
  });

  test('invoices table renders rows with correct data', async ({ page }) => {
    await setupAdmin(page, { invoices: MOCK_INVOICES });
    await page.waitForSelector('#viewTabs', { timeout: 15000 });
    await clickAdminTab(page, 'invoices');
    await page.waitForSelector('#invoices-table', { timeout: 10000 });

    const rows = await page.locator('#invoices-table tr').count();
    expect(rows).toBeGreaterThan(0);
  });

  test('invoices table shows customer name from customer_snapshot.name', async ({ page }) => {
    await setupAdmin(page, { invoices: MOCK_INVOICES });
    await page.waitForSelector('#viewTabs', { timeout: 15000 });
    await clickAdminTab(page, 'invoices');
    await page.waitForSelector('#invoices-table', { timeout: 10000 });

    // Column 3 (index 2) is Customer — now uses customer_snapshot.name
    const customerCell = await page.locator('#invoices-table tr:first-child td:nth-child(3)').textContent();
    expect(customerCell?.trim()).toBe('Alice Smith');
  });

  test('invoices table shows grand_total in Amount column', async ({ page }) => {
    await setupAdmin(page, { invoices: MOCK_INVOICES });
    await page.waitForSelector('#viewTabs', { timeout: 15000 });
    await clickAdminTab(page, 'invoices');
    await page.waitForSelector('#invoices-table', { timeout: 10000 });

    // Column 5 (index 4) is Grand Total
    const totalCell = await page.locator('#invoices-table tr:first-child td:nth-child(5)').textContent();
    expect(totalCell).toContain('109.97');
  });

  test('clicking View does not throw any JS error (Bug 2 fixed)', async ({ page }) => {
    const jsErrors = [];
    page.on('pageerror', err => jsErrors.push(err.message));

    await setupAdmin(page, { invoices: MOCK_INVOICES });
    await page.waitForSelector('#viewTabs', { timeout: 15000 });
    await clickAdminTab(page, 'invoices');
    await page.waitForSelector('#invoices-table', { timeout: 10000 });

    await page.locator('#invoices-table').getByRole('button', { name: 'View' }).first().click();
    await page.waitForTimeout(500);

    // No TypeError from invoice.items.map / invoice.total — the bug is fixed
    const mapErrors = jsErrors.filter(e => e.includes("Cannot read properties of undefined"));
    expect(mapErrors).toHaveLength(0);
  });

  test('clicking View opens modal with invoice number in title', async ({ page }) => {
    await setupAdmin(page, { invoices: MOCK_INVOICES });
    await page.waitForSelector('#viewTabs', { timeout: 15000 });
    await clickAdminTab(page, 'invoices');
    await page.waitForSelector('#invoices-table', { timeout: 10000 });

    await page.locator('#invoices-table').getByRole('button', { name: 'View' }).first().click();

    const modal = page.locator('.pf-v6-c-modal-box');
    await expect(modal).toBeVisible({ timeout: 5000 });

    const title = await modal.locator('.pf-v6-c-modal-box__title').textContent();
    expect(title).toContain('1001');
  });

  test('invoice modal renders line_items rows (not items)', async ({ page }) => {
    await setupAdmin(page, { invoices: MOCK_INVOICES });
    await page.waitForSelector('#viewTabs', { timeout: 15000 });
    await clickAdminTab(page, 'invoices');
    await page.waitForSelector('#invoices-table', { timeout: 10000 });

    await page.locator('#invoices-table').getByRole('button', { name: 'View' }).first().click();
    const modal = page.locator('.pf-v6-c-modal-box');
    await expect(modal).toBeVisible({ timeout: 5000 });

    const content = await modal.locator('#invoice-content').textContent();
    expect(content).toContain('Widget Alpha');
    expect(content).toContain('Gadget Beta');
  });

  test('invoice modal shows customer from customer_snapshot', async ({ page }) => {
    await setupAdmin(page, { invoices: MOCK_INVOICES });
    await page.waitForSelector('#viewTabs', { timeout: 15000 });
    await clickAdminTab(page, 'invoices');
    await page.waitForSelector('#invoices-table', { timeout: 10000 });

    await page.locator('#invoices-table').getByRole('button', { name: 'View' }).first().click();
    const modal = page.locator('.pf-v6-c-modal-box');
    await expect(modal).toBeVisible({ timeout: 5000 });

    const content = await modal.locator('#invoice-content').textContent();
    expect(content).toContain('Alice Smith');
    expect(content).toContain('alice@example.com');
  });

  test('invoice modal shows grand_total (not total)', async ({ page }) => {
    await setupAdmin(page, { invoices: MOCK_INVOICES });
    await page.waitForSelector('#viewTabs', { timeout: 15000 });
    await clickAdminTab(page, 'invoices');
    await page.waitForSelector('#invoices-table', { timeout: 10000 });

    await page.locator('#invoices-table').getByRole('button', { name: 'View' }).first().click();
    const modal = page.locator('.pf-v6-c-modal-box');
    await expect(modal).toBeVisible({ timeout: 5000 });

    const content = await modal.locator('#invoice-content').textContent();
    expect(content).toContain('109.97');
  });

  test('modal Close button dismisses the modal', async ({ page }) => {
    await setupAdmin(page, { invoices: MOCK_INVOICES });
    await page.waitForSelector('#viewTabs', { timeout: 15000 });
    await clickAdminTab(page, 'invoices');
    await page.waitForSelector('#invoices-table', { timeout: 10000 });

    await page.locator('#invoices-table').getByRole('button', { name: 'View' }).first().click();
    const modal = page.locator('.pf-v6-c-modal-box');
    await expect(modal).toBeVisible({ timeout: 5000 });

    // PF6 modals have two close controls: X in the header and Close in the footer
    await modal.locator('.pf-v6-c-modal-box__footer').getByRole('button', { name: 'Close' }).click();
    await page.waitForTimeout(300);
    await expect(modal).not.toBeVisible();
  });

  test('empty invoices state shows placeholder', async ({ page }) => {
    await setupAdmin(page, { invoices: [] });
    await page.waitForSelector('#viewTabs', { timeout: 15000 });
    await clickAdminTab(page, 'invoices');
    await page.waitForSelector('#invoices-table', { timeout: 10000 });

    const emptyCell = await page.locator('#invoices-table .ds-empty-state').textContent();
    expect(emptyCell?.trim()).toBe('No invoices yet.');
  });
});
