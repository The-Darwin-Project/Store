const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

test.describe('Darwin Store Shopping Cart', () => {
  test.beforeEach(async ({ page }) => {
    // Mock the /products API
    await page.route('**/products', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: '1',
            name: 'Test Product',
            sku: 'TEST-001',
            price: 10.00,
            stock: 5,
            image_data: null,
            description: 'Test Description'
          }
        ])
      });
    });

    // Mock the main page
    const htmlPath = path.resolve(__dirname, '../src/app/static/index.html');
    const htmlContent = fs.readFileSync(htmlPath, 'utf8');

    await page.route('http://localhost/', async route => {
        await route.fulfill({
            status: 200,
            contentType: 'text/html',
            body: htmlContent
        });
    });
    
    page.on('console', msg => console.log('PAGE LOG:', msg.text()));
    page.on('pageerror', err => console.log('PAGE ERROR:', err.message));

    await page.goto('http://localhost/');
  });

  test('should display shopping cart icon with badge', async ({ page }) => {
    const cartIcon = page.locator('.cart-icon-wrapper');
    await expect(cartIcon).toBeVisible();
    const badge = page.locator('#cart-badge');
    // Initially hidden if 0 items (logic: badge.classList.toggle('hidden', totalItems === 0))
    await expect(badge).toHaveClass(/hidden/);
    await expect(badge).toHaveText('0');
  });

  test('should add item to cart', async ({ page }) => {
    // Navigate to Catalog tab (Dashboard is now default)
    await page.click('#catalog-tab');
    await page.waitForSelector('.catalog-card');
    
    const addToCartBtn = page.locator('.btn-add-cart').first();
    await expect(addToCartBtn).toBeVisible();
    
    await addToCartBtn.click();
    
    // Check badge update
    const badge = page.locator('#cart-badge');
    await expect(badge).not.toHaveClass(/hidden/);
    await expect(badge).toHaveText('1');

    // Check localStorage
    const cart = await page.evaluate(() => JSON.parse(localStorage.getItem('darwin_cart') || '[]'));
    expect(cart).toHaveLength(1);
    expect(cart[0].id).toBe('1');
    expect(cart[0].qty).toBe(1); // Logic uses 'qty'
  });

  test('should view cart and verify content', async ({ page }) => {
    // Navigate to Catalog tab (Dashboard is now default)
    await page.click('#catalog-tab');
    await page.waitForSelector('.catalog-card');
    // Add item first
    await page.locator('.btn-add-cart').first().click();

    // Open Cart (click icon)
    await page.click('.cart-icon-wrapper');
    
    const cartView = page.locator('#cart'); // Tab pane ID
    await expect(cartView).toBeVisible();
    await expect(cartView).toHaveClass(/active/);
    
    // Check table
    const row = cartView.locator('tbody#cart-table tr').first();
    await expect(row).toContainText('Test Product');
    await expect(row).toContainText('$10.00');
    
    // Check Total
    const total = page.locator('#cart-total');
    await expect(total).toContainText('$10.00');
  });

  test('should update quantity and remove item', async ({ page }) => {
    // Navigate to Catalog tab (Dashboard is now default)
    await page.click('#catalog-tab');
    await page.waitForSelector('.catalog-card');
    // Add item
    await page.locator('.btn-add-cart').first().click();
    await page.click('.cart-icon-wrapper');

    // Increase Qty
    // The buttons in remote logic: <button onclick="updateCartQty(..., 1)">+</button>
    // Selector needs to be specific.
    // .cart-qty-controls button with text '+'
    await page.click('.cart-qty-controls button:has-text("+")');
    
    const qty = page.locator('.cart-qty-controls span');
    await expect(qty).toHaveText('2');
    await expect(page.locator('#cart-total')).toContainText('$20.00');

    // Decrease Qty
    await page.click('.cart-qty-controls button:has-text("-")');
    await expect(qty).toHaveText('1');
    
    // Remove
    await page.click('button.danger:has-text("Remove")');
    
    // Check empty state
    const emptyMsg = page.locator('#cart-table .empty-state');
    await expect(emptyMsg).toBeVisible();
    
    // Badge should be hidden or 0
    const badge = page.locator('#cart-badge');
    await expect(badge).toHaveClass(/hidden/);
    await expect(badge).toHaveText('0');
  });
});
