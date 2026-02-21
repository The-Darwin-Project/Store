const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

test.describe('Unassigned Orders UI Feature', () => {
  const MOCK_CUSTOMER_ID = 'cust-123';
  const MOCK_ASSIGNED_ORDER_ID = 'order-assigned-1';
  const MOCK_UNASSIGNED_ORDER_ID_1 = 'order-1-unassigned';
  const MOCK_UNASSIGNED_ORDER_ID_2 = 'order-2-unassigned';

  test.beforeEach(async ({ page }) => {
    // 1. Mock /products (needed for initial load)
    await page.route('**/products', async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
    });

    // 2. Mock /customers (for attach modal)
    await page.route('**/customers', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([{
          id: MOCK_CUSTOMER_ID,
          name: 'Test Customer',
          email: 'test@example.com',
          created_at: new Date().toISOString()
        }])
      });
    });

    // 3. Mock /orders (Assigned orders for main table)
    await page.route('**/orders', async route => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([{
            id: MOCK_ASSIGNED_ORDER_ID,
            created_at: new Date().toISOString(),
            total_amount: 50.00,
            status: 'confirmed',
            customer_id: MOCK_CUSTOMER_ID,
            items: []
          }])
        });
      } else {
        await route.continue();
      }
    });

    // 4. Mock /orders/unassigned
    await page.route('**/orders/unassigned', async route => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify([
                {
                    id: MOCK_UNASSIGNED_ORDER_ID_1,
                    created_at: new Date().toISOString(),
                    total_amount: 25.00,
                    status: 'pending',
                    customer_id: null,
                    items: []
                },
                {
                    id: MOCK_UNASSIGNED_ORDER_ID_2,
                    created_at: new Date().toISOString(),
                    total_amount: 75.00,
                    status: 'shipped',
                    customer_id: null,
                    items: []
                }
            ])
        });
    });

    // 5. Mock Attach: PUT /orders/{id}/customer/{cid}
    await page.route(`**/orders/${MOCK_UNASSIGNED_ORDER_ID_1}/customer/${MOCK_CUSTOMER_ID}`, async route => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                id: MOCK_UNASSIGNED_ORDER_ID_1,
                created_at: new Date().toISOString(),
                total_amount: 25.00,
                status: 'pending',
                customer_id: MOCK_CUSTOMER_ID
            })
        });
    });

    // 6. Mock Delete: DELETE /orders/{id}
    await page.route(`**/orders/${MOCK_UNASSIGNED_ORDER_ID_2}`, async route => {
        if (route.request().method() === 'DELETE') {
            await route.fulfill({ status: 204 });
        }
    });

    // Load the local HTML file
    // We assume the test runs from the root or tests dir, trying to locate src/app/static/index.html
    // The previous test used path.resolve(__dirname, '../src/app/static/index.html');
    // We'll trust that structure.
    const htmlPath = path.resolve(__dirname, '../src/app/static/index.html');
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

  test('should display unassigned orders in the Orders tab', async ({ page }) => {
    await page.click('#orders-tab');
    
    // Verify "Unassigned Orders (Legacy)" panel
    await expect(page.locator('h2', { hasText: 'Unassigned Orders (Legacy)' })).toBeVisible();
    
    // Verify order list
    const table = page.locator('#unassigned-orders-table');
    await expect(table).toContainText(MOCK_UNASSIGNED_ORDER_ID_1.substring(0, 8));
    await expect(table).toContainText(MOCK_UNASSIGNED_ORDER_ID_2.substring(0, 8));
  });

  test('should attach an unassigned order to a customer', async ({ page }) => {
    await page.click('#orders-tab');
    
    // Find the row for order 1
    const row = page.locator('#unassigned-orders-table tr', { hasText: MOCK_UNASSIGNED_ORDER_ID_1.substring(0, 8) });
    
    // Click Attach
    await row.locator('button:has-text("Attach")').click();
    
    // Expect modal to appear
    await expect(page.locator('#attach-modal')).toHaveClass(/active/);
    
    // Select customer
    await page.selectOption('#attach-customer-select', MOCK_CUSTOMER_ID);
    
    // Click Confirm Attach (button text is "Attach")
    await page.click('#attach-modal button:has-text("Attach")');
    
    // Verify log success message
    await expect(page.locator('#log')).toContainText(`Order ${MOCK_UNASSIGNED_ORDER_ID_1.substring(0, 8)}... attached to customer`);
    
    // Modal should close
    await expect(page.locator('#attach-modal')).not.toHaveClass(/active/);
  });

  test('should delete an unassigned order', async ({ page }) => {
    await page.click('#orders-tab');
    
    // Handle dialog
    page.on('dialog', dialog => dialog.accept());
    
    // Find row for order 2
    const row = page.locator('#unassigned-orders-table tr', { hasText: MOCK_UNASSIGNED_ORDER_ID_2.substring(0, 8) });
    
    // Click Delete
    await row.locator('button:has-text("Delete")').click();
    
    // Verify log success message
    await expect(page.locator('#log')).toContainText(`Deleted order ${MOCK_UNASSIGNED_ORDER_ID_2.substring(0, 8)}...`);
  });
});
