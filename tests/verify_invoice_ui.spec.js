const { test, expect } = require('@playwright/test');

test.describe('Customer Invoice System UI', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the app (assuming it's running on localhost:8080)
    // We mock the API responses to make the test self-contained
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
            company: 'Acme Corporation',
            shipping_street: '123 Main St',
            shipping_city: 'Metropolis'
          },
          line_items: [
            { product_name: 'Gadget', sku: 'G1', unit_price: 100.0, quantity: 2, line_total: 200.0 }
          ],
          subtotal: 200.0,
          grand_total: 200.0,
          created_at: new Date().toISOString()
        })
      });
    });

    // Mock index.html if necessary or just use the real one if we can assume it's served
    await page.goto('http://localhost:8080');
  });

  test('Customer form includes new fields', async ({ page }) => {
    await page.click('#customers-tab');
    
    // Check for new fields in the Add Customer form
    // Note: IDs are based on the plan's suggestions or expected implementation
    const companyField = page.locator('#cust-company');
    const phoneField = page.locator('#cust-phone');
    const streetField = page.locator('#cust-street');
    const cityField = page.locator('#cust-city');
    
    // These should exist if implemented
    await expect(companyField).toBeVisible();
    await expect(phoneField).toBeVisible();
    await expect(streetField).toBeVisible();
    await expect(cityField).toBeVisible();
  });

  test('Orders tab shows Invoice buttons for delivered orders', async ({ page }) => {
    await page.click('#orders-tab');
    
    // Wait for orders to load
    await page.waitForSelector('.order-row');
    
    // Find order-1 (no invoice_id)
    const order1Row = page.locator('.order-row:has-text("order-1")');
    const genInvoiceBtn = order1Row.locator('button:has-text("Generate Invoice")');
    await expect(genInvoiceBtn).toBeVisible();
    
    // Find order-2 (has invoice_id)
    const order2Row = page.locator('.order-row:has-text("order-2")');
    const viewInvoiceBtn = order2Row.locator('button:has-text("View Invoice")');
    await expect(viewInvoiceBtn).toBeVisible();
  });

  test('Invoice modal displays content correctly', async ({ page }) => {
    await page.click('#orders-tab');
    await page.waitForSelector('.order-row');
    
    const viewInvoiceBtn = page.locator('button:has-text("View Invoice")').first();
    await viewInvoiceBtn.click();
    
    // Check modal visibility
    const modal = page.locator('#invoice-modal');
    await expect(modal).toHaveClass(/active/);
    
    // Check content
    const content = page.locator('#invoice-content');
    await expect(content).toContainText('Invoice INV-0101');
    await expect(content).toContainText('Acme Corporation');
    await expect(content).toContainText('123 Main St');
    await expect(content).toContainText('Gadget');
    await expect(content).toContainText('$200.00');
    
    // Check for print button
    const printBtn = page.locator('button:has-text("Print")');
    await expect(printBtn).toBeVisible();
    
    // Close modal
    await page.click('button:has-text("Close")');
    await expect(modal).not.toHaveClass(/active/);
  });
});
