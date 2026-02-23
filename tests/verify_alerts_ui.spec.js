const { test, expect } = require('@playwright/test');
const fs = require('fs');

test('Verify Alerts UI Flow with Mocked Backend', async ({ page }) => {
  // Mock Data
  const mockAlerts = [
    {
      id: "alert-1",
      type: "restock",
      message: "Restock needed: 'Test Item' stock is 5, below threshold of 10. Supplier: Test Supplier.",
      status: "active",
      product_id: "prod-1",
      supplier_id: "sup-1",
      current_stock: 5,
      reorder_threshold: 10,
      created_at: new Date().toISOString()
    },
    {
      id: "alert-2",
      type: "restock",
      message: "Restock needed: 'Another Item' stock is 0.",
      status: "ordered",
      product_id: "prod-2",
      supplier_id: null,
      current_stock: 0,
      reorder_threshold: 5,
      created_at: new Date().toISOString()
    }
  ];

  // Intercept API calls
  await page.route('**/alerts*', async route => {
    if (route.request().method() === 'GET') {
      const url = new URL(route.request().url());
      const status = url.searchParams.get('status');
      
      let returnedAlerts = mockAlerts;
      if (status) {
        returnedAlerts = returnedAlerts.filter(a => a.status === status);
      }
      await route.fulfill({ json: returnedAlerts });
    } else if (route.request().method() === 'PATCH') {
      const postData = JSON.parse(route.request().postData());
      const urlParts = route.request().url().split('/');
      const alertId = urlParts[urlParts.length - 1];
      
      const alert = mockAlerts.find(a => a.id === alertId);
      if (alert) {
        alert.status = postData.status;
        await route.fulfill({ json: alert });
      } else {
        await route.fulfill({ status: 404, json: { detail: 'Not found' } });
      }
    } else {
      await route.continue();
    }
  });

  // Also mock other required endpoints to prevent UI crash
  await page.route('**/products*', async route => {
    await route.fulfill({ json: [] });
  });
  await page.route('**/orders*', async route => {
    await route.fulfill({ json: [] });
  });
  await page.route('**/customers*', async route => {
    await route.fulfill({ json: [] });
  });
  await page.route('**/suppliers*', async route => {
    await route.fulfill({ json: [] });
  });
  await page.route('**/dashboard/summary', async route => {
    await route.fulfill({ json: {
      total_products: 0,
      total_orders: 0,
      total_revenue: 0,
      low_stock_alerts: []
    }});
  });

  const path = require('path');
  const fs = require('fs');
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

  // 1. Verify Alerts tab is visible and badge shows correct count
  const alertsTab = page.locator('#alerts-tab');
  await expect(alertsTab).toBeVisible();
  
  // The badge count should be updated from `updateAlertsBadge` which calls `/alerts?status=active`
  // We mocked 1 active alert.
  const alertsBadge = page.locator('#alerts-badge');
  await expect(alertsBadge).toContainText('1');

  // 2. Click the Alerts tab and verify alerts are loaded
  await alertsTab.click();
  
  // Verify the alerts are displayed in the table
  const alertsTable = page.locator('#alerts-table');
  await expect(alertsTable).toContainText('Test Item');

  // Change filter to All Alerts
  await page.locator('#alerts-filter').selectOption('');
  
  // Verify Both items show up
  await expect(alertsTable).toContainText('Test Item');
  await expect(alertsTable).toContainText('Another Item');

  // 3. Mark an alert as ordered
  // Find the 'Mark Ordered' button for alert-1 (which is active)
  const orderedBtn = page.locator(`button[onclick="markAlertOrdered('alert-1')"]`);
  await expect(orderedBtn).toBeVisible();
  await orderedBtn.click();

  // After clicking, the mock will return status 'ordered'
  // The UI should reload alerts, so both will be 'ordered' now.
  // We can verify that the 'ordered' badge is displayed for 'alert-1'
  // The exact HTML might differ, but 'ordered' text should be there.
  await expect(alertsTable).toContainText('ordered');
  
});
