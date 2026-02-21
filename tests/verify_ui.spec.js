const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

test.describe('Darwin Store UI Redesign', () => {
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
              name: 'Test Product',
              sku: 'TEST-001',
              price: 10.99,
              stock: 5,
              image_data: null,
              description: 'This is a test description.'
            },
            {
              id: '2',
              name: 'Out of Stock Product',
              sku: 'TEST-002',
              price: 20.00,
              stock: 0,
              image_data: null,
              description: ''
            }
          ])
        });
      } else if (method === 'POST') {
        const postData = route.request().postDataJSON();
        await route.fulfill({
            status: 201,
            contentType: 'application/json',
            body: JSON.stringify({
                id: '3',
                ...postData
            })
        });
      } else {
        await route.continue();
      }
    });

    // Mock other API endpoints used at init
    await page.route('**/suppliers', async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
    });
    await page.route('**/customers', async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
    });
    await page.route('**/orders**', async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
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

  test('should verify tab structure and default view', async ({ page }) => {
    // Check if Tabs exist
    const catalogTab = page.locator('#catalog-tab');
    const inventoryTab = page.locator('#inventory-tab');
    
    await expect(catalogTab).toBeVisible();
    await expect(inventoryTab).toBeVisible();
    await expect(catalogTab).toHaveText('Catalog');
    await expect(inventoryTab).toHaveText('Inventory');

    // Check default view (Catalog should be active)
    await expect(catalogTab).toHaveClass(/active/);
    await expect(page.locator('#catalog')).toBeVisible(); // Check content visibility if possible, or class
    await expect(page.locator('#catalog')).toHaveClass(/active/);
    
    // Inventory should be hidden/inactive
    await expect(inventoryTab).not.toHaveClass(/active/);
    await expect(page.locator('#inventory')).not.toHaveClass(/active/);
  });

  test('should render Catalog correctly', async ({ page }) => {
    // Ensure we are on Catalog tab
    await page.click('#catalog-tab');
    
    // Check for grid items
    const cards = page.locator('.catalog-card');
    await expect(cards).toHaveCount(2);

    // Check content of first card
    const firstCard = cards.first();
    await expect(firstCard.locator('h3')).toHaveText('Test Product');
    await expect(firstCard.locator('.card-price')).toHaveText('$10.99');
    await expect(firstCard.locator('.stock-badge')).toHaveText('In Stock');
    await expect(firstCard.locator('.stock-badge')).toHaveClass(/in-stock/);

    // Check content of second card (Out of Stock)
    const secondCard = cards.nth(1);
    await expect(secondCard.locator('h3')).toHaveText('Out of Stock Product');
    await expect(secondCard.locator('.stock-badge')).toHaveText('Out of Stock');
    await expect(secondCard.locator('.stock-badge')).toHaveClass(/out-of-stock/);
    
    // Verify no edit buttons in catalog
    // Note: We added "Add to Cart" buttons, but Edit buttons are in Inventory.
    // The original test checked for buttons count=0 or specific buttons?
    // "await expect(firstCard.locator('button')).toHaveCount(0);"
    // This will now FAIL because we added "Add to Cart".
    // We should update expectation to expect 1 button (Add to Cart).
    await expect(firstCard.locator('button')).toHaveCount(1);
    await expect(firstCard.locator('button')).toHaveText('Add to Cart');
  });

  test('should render Inventory correctly with description', async ({ page }) => {
    // Switch to Inventory tab
    await page.click('#inventory-tab');
    
    // Check for table
    // Use more specific locator
    const table = page.locator('#inventory table');
    await expect(table).toBeVisible();

    // Check Headers
    const headers = table.locator('th');
    await expect(headers).toContainText(['Description']);

    // Check Rows
    const rows = table.locator('tbody tr');
    await expect(rows).toHaveCount(2);

    // Check Description cell
    const firstRow = rows.first();
    await expect(firstRow.locator('td').nth(6)).toHaveText('This is a test description.'); // 7th column (index 6) is Description (Supplier is at index 5)
  });

  test('should have description field in Add Product form', async ({ page }) => {
    await page.click('#inventory-tab');
    
    const addForm = page.locator('#add-form');
    await expect(addForm).toBeVisible();
    
    const descInput = addForm.locator('#add-description');
    await expect(descInput).toBeVisible();
    await expect(descInput).toHaveAttribute('placeholder', /Product description/);
  });

  test('should have description field in Edit Product modal', async ({ page }) => {
    await page.click('#inventory-tab');
    
    // Click Edit on first item
    await page.click('button:has-text("Edit") >> nth=0');
    
    const editModal = page.locator('#edit-modal');
    await expect(editModal).toHaveClass(/active/);
    
    const descInput = editModal.locator('#edit-description');
    await expect(descInput).toBeVisible();
    await expect(descInput).toHaveValue('This is a test description.');
  });
});
