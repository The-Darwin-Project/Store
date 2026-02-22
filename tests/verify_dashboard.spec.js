const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

test.describe('Darwin Store Dashboard UI', () => {
  test.beforeEach(async ({ page }) => {
    // Load the local HTML file
    const htmlPath = path.resolve(__dirname, '../src/app/static/index.html');
    const htmlContent = fs.readFileSync(htmlPath, 'utf8');

    await page.route('http://localhost/', async route => {
        await route.fulfill({
            status: 200,
            contentType: 'text/html',
            body: htmlContent
        });
    });

    // Mock products API
    await page.route('**/products', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([])
      });
    });
  });

  test('should verify the dashboard is the default landing page and displays metrics', async ({ page }) => {
    // Mock the dashboard API
    await page.route('**/dashboard', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          total_revenue: 1234.56,
          orders_by_status: {
            "pending": 2,
            "shipped": 5
          },
          top_products: [
            { name: "Top Product 1", total_sold: 50 },
            { name: "Top Product 2", total_sold: 40 }
          ],
          low_stock_alerts: [
            {
              name: "Low Stock Prod",
              stock: 2,
              reorder_threshold: 10,
              supplier: { name: "Supplier A", contact_email: "a@a.com" }
            }
          ]
        })
      });
    });

    await page.goto('http://localhost/');

    // 1. Verify dashboard is default landing page
    const dashboardTab = page.locator('#dashboard-tab');
    await expect(dashboardTab).toBeVisible();
    await expect(dashboardTab).toHaveClass(/active/);
    await expect(page.locator('#dashboard')).toBeVisible();

    // 2. Verify total revenue calculation is accurate
    await expect(page.locator('#dashboard-revenue')).toHaveText('$1234.56');

    // 3. Verify order counts by status are correct
    const statusContainer = page.locator('#dashboard-orders-status');
    await expect(statusContainer).toContainText('pending: 2');
    await expect(statusContainer).toContainText('shipped: 5');

    // 4. Verify top products list
    const topTbody = page.locator('#dashboard-top-products');
    await expect(topTbody).toContainText('Top Product 1');
    await expect(topTbody).toContainText('50');

    // 5. Verify low-stock alerts
    const lowTbody = page.locator('#dashboard-low-stock');
    await expect(lowTbody).toContainText('Low Stock Prod');
    await expect(lowTbody).toContainText('2'); // stock
    await expect(lowTbody).toContainText('Supplier A');
    await expect(lowTbody).toContainText('a@a.com');
  });

  test('should handle empty states gracefully', async ({ page }) => {
    // Mock the dashboard API with empty states
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

    await page.goto('http://localhost/');

    // Verify empty states
    await expect(page.locator('#dashboard-revenue')).toHaveText('$0.00');
    await expect(page.locator('#dashboard-orders-status')).toHaveText('No orders yet.');
    await expect(page.locator('#dashboard-top-products')).toContainText('No sales data yet.');
    await expect(page.locator('#dashboard-low-stock')).toContainText('No low-stock items.');
  });
});
