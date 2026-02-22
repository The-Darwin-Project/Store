const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

test.describe('Real-Time Search Bar', () => {
  test.beforeEach(async ({ page }) => {
    // Mock the /products API
    await page.route('**/products', async route => {
      const method = route.request().method();
      if (method === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: '1',
              name: 'Apple iPad',
              sku: 'IPAD-123',
              price: 500.00,
              stock: 10,
              image_data: null,
              description: 'A great tablet'
            },
            {
              id: '2',
              name: 'Banana',
              sku: 'BNNA-456',
              price: 1.00,
              stock: 100,
              image_data: null,
              description: 'A yellow fruit'
            }
          ])
        });
      } else {
        await route.continue();
      }
    });

    // Mock unassigned orders (must be registered before /orders to match first)
    await page.route('**/orders/unassigned', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([])
      });
    });

    // Mock orders
    await page.route('**/orders', async route => {
      const method = route.request().method();
      if (method === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: 'ORD-001-abcdefgh',
              created_at: new Date().toISOString(),
              status: 'pending',
              total_amount: 150.00,
              items: []
            },
            {
              id: 'ORD-002-ijklmnop',
              created_at: new Date().toISOString(),
              status: 'shipped',
              total_amount: 300.00,
              items: []
            }
          ])
        });
      } else {
        await route.continue();
      }
    });

    // Mock suppliers
    await page.route('**/suppliers', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: '1',
            name: 'TechCorp',
            contact_email: 'tech@corp.com',
            phone: '1234567890',
            low_stock_count: 0
          },
          {
            id: '2',
            name: 'FoodInc',
            contact_email: 'food@inc.com',
            phone: '0987654321',
            low_stock_count: 0
          }
        ])
      });
    });

    // Mock customers
    await page.route('**/customers', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: '1',
            name: 'John Doe',
            email: 'john@doe.com'
          },
          {
            id: '2',
            name: 'Jane Smith',
            email: 'jane@smith.com'
          }
        ])
      });
    });

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

    await page.goto('http://localhost/');
  });

  test('should filter products in Catalog and Inventory tabs', async ({ page }) => {
    const searchInput = page.locator('#global-search');
    await expect(searchInput).toBeVisible();

    // Default Catalog tab
    await expect(page.locator('#catalog-tab')).toHaveClass(/active/);
    
    // Ensure 2 items initially
    await expect(page.locator('.catalog-card')).toHaveCount(2);

    // Search for "Apple"
    await searchInput.fill('Apple');
    await expect(page.locator('.catalog-card')).toHaveCount(1);
    await expect(page.locator('.catalog-card').first()).toContainText('Apple iPad');

    // Switch to Inventory tab, search should persist
    await page.click('#inventory-tab');
    await expect(page.locator('#product-table tr')).toHaveCount(1);
    await expect(page.locator('#product-table tr').first()).toContainText('Apple iPad');

    // Clear search, should restore all items
    await searchInput.fill('');
    await expect(page.locator('#product-table tr')).toHaveCount(2);

    // Switch back to catalog and verify all items are there
    await page.click('#catalog-tab');
    await expect(page.locator('.catalog-card')).toHaveCount(2);
  });

  test('should filter orders correctly', async ({ page }) => {
    // Switch to Orders tab
    await page.click('#orders-tab');
    
    const searchInput = page.locator('#global-search');
    
    // Wait for initial load
    await expect(page.locator('#orders-table tr')).toHaveCount(2);

    // Search for "ORD-001"
    await searchInput.fill('ORD-001');
    await expect(page.locator('#orders-table tr')).toHaveCount(1);
    await expect(page.locator('#orders-table tr').first()).toContainText('ORD-001');

    // Search for status "shipped"
    await searchInput.fill('shipped');
    await expect(page.locator('#orders-table tr')).toHaveCount(1);
    await expect(page.locator('#orders-table tr').first()).toContainText('ORD-002');
  });

  test('should filter suppliers correctly', async ({ page }) => {
    // Switch to Suppliers tab
    await page.click('#suppliers-tab');
    
    const searchInput = page.locator('#global-search');
    
    await expect(page.locator('#supplier-list .customer-list-item')).toHaveCount(2);

    // Search for "TechCorp"
    await searchInput.fill('TechCorp');
    await expect(page.locator('#supplier-list .customer-list-item')).toHaveCount(1);
    await expect(page.locator('#supplier-list .customer-list-item').first()).toContainText('TechCorp');
    
    // Search for email "food"
    await searchInput.fill('food@inc.com');
    await expect(page.locator('#supplier-list .customer-list-item')).toHaveCount(1);
    await expect(page.locator('#supplier-list .customer-list-item').first()).toContainText('FoodInc');
  });

  test('should retain search across periodic refreshes', async ({ page }) => {
    // Search for "Banana" in catalog
    const searchInput = page.locator('#global-search');
    await searchInput.fill('Banana');
    await expect(page.locator('.catalog-card')).toHaveCount(1);
    await expect(page.locator('.catalog-card').first()).toContainText('Banana');

    // Trigger window.loadProducts manually to simulate periodic refresh
    await page.evaluate(() => {
      if (typeof window.loadProducts === 'function') {
        return window.loadProducts();
      }
    });

    // Make sure only 1 item remains after refresh
    await expect(page.locator('.catalog-card')).toHaveCount(1);
    await expect(page.locator('.catalog-card').first()).toContainText('Banana');
  });
});
