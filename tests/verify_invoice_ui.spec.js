const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

test.describe('Customer Invoice System UI', () => {
  test.beforeEach(async ({ page }) => {
    // Mock /products
    await page.route('**/products', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([])
      });
    });

    // Mock /suppliers
    await page.route('**/suppliers', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([])
      });
    });

    // Mock /dashboard
    await page.route('**/dashboard', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          total_revenue: 0,
          orders_by_status: {},
          top_products: [],
          low_stock_alerts: []
        })
      });
    });

    // Mock /alerts
    await page.route('**/alerts**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([])
      });
    });

    // Mock /customers
    await page.route('**/customers', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'cust-1',
            name: 'Acme Corp',
            email: 'acme@example.com',
            company: 'Acme Corporation',
            phone: '555-0123',
            shipping_street: '123 Main St',
            shipping_city: 'Metropolis',
            shipping_state: 'NY',
            shipping_zip: '10001',
            shipping_country: 'USA',
            created_at: new Date().toISOString()
          }
        ])
      });
    });

    // Mock /orders (GET)
    await page.route('**/orders', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'order-1',
            created_at: new Date().toISOString(),
            total_amount: 150.0,
            status: 'delivered',
            customer_id: 'cust-1',
            customer_name: 'Acme Corp',
            items: [],
            invoice_id: null
          },
          {
            id: 'order-2',
            created_at: new Date().toISOString(),
            total_amount: 200.0,
            status: 'delivered',
            customer_id: 'cust-1',
            customer_name: 'Acme Corp',
            items: [],
            invoice_id: 'inv-1'
          }
        ])
      });
    });

    // Mock /orders/unassigned
    await page.route('**/orders/unassigned', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([])
      });
    });

    // Mock /invoices/inv-1
    await page.route('**/invoices/inv-1', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'inv-1',
          invoice_number: 101,
          order_id: 'order-2',
          customer_snapshot: {
            name: 'Acme Corp',
            email: 'acme@example.com',
            company: 'Acme Corporation',
            shipping_street: '123 Main St',
            shipping_city: 'Metropolis',
            shipping_state: 'NY',
            shipping_zip: '10001',
            shipping_country: 'USA'
          },
          line_items: [
            { product_name: 'Gadget', sku: 'G1', unit_price: 100.0, quantity: 2, line_total: 200.0 }
          ],
          subtotal: 200.0,
          discount_amount: 0.0,
          grand_total: 200.0,
          created_at: new Date().toISOString()
        })
      });
    });

    // Serve HTML from file system
    const htmlPath = path.resolve(__dirname, '../src/app/static/admin.html');
    const htmlContent = fs.readFileSync(htmlPath, 'utf8');

    await page.route('http://localhost/', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'text/html',
        body: htmlContent
      });
    });

    await page.goto('http://localhost/');
  });

  test('Customer form includes new fields', async ({ page }) => {
    await page.click('#customers-tab');

    const companyField = page.locator('#cust-company');
    const phoneField = page.locator('#cust-phone');
    const streetField = page.locator('#cust-street');
    const cityField = page.locator('#cust-city');

    await expect(companyField).toBeVisible();
    await expect(phoneField).toBeVisible();
    await expect(streetField).toBeVisible();
    await expect(cityField).toBeVisible();
  });

  test('Orders tab shows Invoice buttons for delivered orders', async ({ page }) => {
    await page.click('#orders-tab');

    await page.waitForSelector('.order-row');

    // order-1 has no invoice - should show Generate Invoice
    const genInvoiceBtn = page.locator('button:has-text("Generate Invoice")');
    await expect(genInvoiceBtn).toBeVisible();

    // order-2 has invoice_id - should show View Invoice
    const viewInvoiceBtn = page.locator('button:has-text("View Invoice")');
    await expect(viewInvoiceBtn).toBeVisible();
  });

  test('Invoice modal displays content correctly', async ({ page }) => {
    await page.click('#orders-tab');
    await page.waitForSelector('.order-row');

    const viewInvoiceBtn = page.locator('button:has-text("View Invoice")').first();
    await viewInvoiceBtn.click();

    const modal = page.locator('#invoice-modal');
    await expect(modal).toHaveClass(/active/);

    const content = page.locator('#invoice-content');
    await expect(content).toContainText('Invoice INV-0101');
    await expect(content).toContainText('Acme Corporation');
    await expect(content).toContainText('123 Main St');
    await expect(content).toContainText('Gadget');
    await expect(content).toContainText('$200.00');

    const printBtn = page.locator('button:has-text("Print")');
    await expect(printBtn).toBeVisible();

    await page.click('button:has-text("Close")');
    await expect(modal).not.toHaveClass(/active/);
  });
});
