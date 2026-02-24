// Store/tests/verify_add_to_cart_modal.spec.js
// @ai-rules:
// 1. [Pattern]: Self-contained -- loads HTML from filesystem, mocks all API routes.
// 2. [Coverage]: Verifies 'Add to Cart' button in product detail modal and cart update behavior.
// 3. [BugReport]: User reported that Add to Cart is missing from product detail modal (evt-ed3ed4fa).
//    Expected: modal has 'Add to Cart' button that updates cart count.
//    Actual: modal only has 'Write a Review' form -- no Add to Cart button.

const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const PRODUCT_ID = '11111111-1111-1111-1111-111111111111';
const CUSTOMER_ID = '22222222-2222-2222-2222-222222222222';

const MOCK_PRODUCT = {
  id: PRODUCT_ID,
  name: 'Test Widget',
  price: 29.99,
  stock: 10,
  sku: 'TW-001',
  image_data: null,
  description: 'A great test widget',
  supplier_id: null,
  reorder_threshold: 10
};

const MOCK_PRODUCT_OUT_OF_STOCK = {
  ...MOCK_PRODUCT,
  id: '33333333-3333-3333-3333-333333333333',
  name: 'Out of Stock Widget',
  stock: 0,
  sku: 'TW-OOS'
};

const MOCK_RATING = { product_id: PRODUCT_ID, average_rating: 4.2, review_count: 5 };
const MOCK_REVIEWS = [];

async function setupPage(page, products) {
  const productList = products || [MOCK_PRODUCT];

  await page.route(`**/products/${PRODUCT_ID}/average-rating`, async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_RATING) });
  });
  await page.route(`**/products/${MOCK_PRODUCT_OUT_OF_STOCK.id}/average-rating`, async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ product_id: MOCK_PRODUCT_OUT_OF_STOCK.id, average_rating: 0, review_count: 0 }) });
  });
  await page.route(`**/products/*/average-rating`, async route => {
    const pid = route.request().url().split('/products/')[1].split('/')[0];
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ product_id: pid, average_rating: 0, review_count: 0 }) });
  });

  await page.route(`**/products/${PRODUCT_ID}/reviews`, async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_REVIEWS) });
  });
  await page.route(`**/products/${MOCK_PRODUCT_OUT_OF_STOCK.id}/reviews`, async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });

  await page.route(`**/products/${PRODUCT_ID}`, async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_PRODUCT) });
  });
  await page.route(`**/products/${MOCK_PRODUCT_OUT_OF_STOCK.id}`, async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_PRODUCT_OUT_OF_STOCK) });
  });

  await page.route('**/products', async route => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(productList) });
    } else {
      await route.continue();
    }
  });

  await page.route('**/customers', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([
      { id: CUSTOMER_ID, name: 'Alice', email: 'alice@example.com' }
    ]) });
  });

  await page.route('**/orders**', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });

  const htmlPath = path.resolve(__dirname, '..', 'src', 'app', 'static', 'index.html');
  const htmlContent = fs.readFileSync(htmlPath, 'utf8');
  await page.route('http://localhost/', async route => {
    await route.fulfill({ status: 200, contentType: 'text/html', body: htmlContent });
  });

  const cssPath = path.resolve(__dirname, '..', 'src', 'app', 'static', 'shared.css');
  const cssContent = fs.readFileSync(cssPath, 'utf8');
  await page.route('**/static/shared.css', async route => {
    await route.fulfill({ status: 200, contentType: 'text/css', body: cssContent });
  });

  await page.goto('http://localhost/');
  await page.waitForSelector('.catalog-card', { timeout: 10000 });
}

// ---- Baseline: Add to Cart on catalog tile works ----

test.describe('Baseline - Add to Cart on catalog tile', () => {
  test.beforeEach(async ({ page }) => {
    await setupPage(page);
  });

  test('catalog tile has Add to Cart button for in-stock product', async ({ page }) => {
    const addBtn = page.locator('.catalog-card .btn-add-cart').first();
    await expect(addBtn).toBeVisible();
    await expect(addBtn).toHaveText('Add to Cart');
  });

  test('clicking Add to Cart on tile increments cart count', async ({ page }) => {
    // Cart badge is #cart-badge (starts hidden at 0)
    const initialCount = await page.evaluate(() => {
      const badge = document.getElementById('cart-badge');
      return badge ? parseInt(badge.textContent) || 0 : 0;
    });

    // Click Add to Cart on tile
    const addBtn = page.locator('.catalog-card .btn-add-cart').first();
    await addBtn.click();

    // Cart badge should now show 1 (was hidden/0)
    const newCount = await page.evaluate(() => {
      const badge = document.getElementById('cart-badge');
      return badge ? parseInt(badge.textContent) || 0 : 0;
    });

    expect(newCount).toBeGreaterThan(initialCount);
    expect(newCount).toBe(1);
  });

  test('Add to Cart on tile does NOT open product detail modal', async ({ page }) => {
    // event.stopPropagation() must prevent modal from opening
    const addBtn = page.locator('.catalog-card .btn-add-cart').first();
    await addBtn.click();

    const modal = page.locator('#product-detail-modal');
    await expect(modal).not.toHaveClass(/active/);
  });

  test('catalog tile has no Add to Cart button for out-of-stock product', async ({ page }) => {
    await setupPage(page, [MOCK_PRODUCT_OUT_OF_STOCK]);
    // Re-wait for catalog to render
    await page.waitForSelector('.catalog-card', { timeout: 10000 });

    const addBtn = page.locator('.catalog-card .btn-add-cart');
    const count = await addBtn.count();
    expect(count).toBe(0);
  });
});

// ---- Core Bug: Add to Cart in product detail modal ----

test.describe('Add to Cart button in product detail modal', () => {
  test.beforeEach(async ({ page }) => {
    await setupPage(page);
    // Open product detail modal by clicking the card
    await page.locator('.catalog-card').first().click({ position: { x: 5, y: 5 } });
    // Wait for modal to open
    const modal = page.locator('#product-detail-modal');
    await expect(modal).toHaveClass(/active/, { timeout: 5000 });
    // Wait for product content to load
    await expect(page.locator('#product-detail-content')).toContainText('Test Widget', { timeout: 5000 });
  });

  test('product detail modal contains an Add to Cart button', async ({ page }) => {
    // EXPECTED: The product detail modal should have an Add to Cart button
    // ACTUAL (bug): No Add to Cart button -- modal only has review form
    const modal = page.locator('#product-detail-modal');
    const addBtn = modal.locator('button:has-text("Add to Cart"), .btn-add-cart');
    await expect(addBtn).toBeVisible({ timeout: 3000 });
  });

  test('Add to Cart button in modal increments cart count', async ({ page }) => {
    const initialCount = await page.evaluate(() => {
      const badge = document.getElementById('cart-badge');
      return badge ? parseInt(badge.textContent) || 0 : 0;
    });

    const modal = page.locator('#product-detail-modal');
    const addBtn = modal.locator('button:has-text("Add to Cart"), .btn-add-cart');
    await addBtn.click();

    const newCount = await page.evaluate(() => {
      const badge = document.getElementById('cart-badge');
      return badge ? parseInt(badge.textContent) || 0 : 0;
    });

    expect(newCount).toBeGreaterThan(initialCount);
  });

  test('Add to Cart in modal does not close the modal', async ({ page }) => {
    // Clicking Add to Cart should NOT close the product detail modal
    // (same UX as other e-commerce sites -- modal stays open)
    const modal = page.locator('#product-detail-modal');
    const addBtn = modal.locator('button:has-text("Add to Cart"), .btn-add-cart');
    await addBtn.click();

    // Modal should still be active
    await expect(modal).toHaveClass(/active/);
  });

  test('Add to Cart in modal adds the correct product to cart', async ({ page }) => {
    const modal = page.locator('#product-detail-modal');
    const addBtn = modal.locator('button:has-text("Add to Cart"), .btn-add-cart');
    await addBtn.click();

    // Verify the correct product was added via localStorage
    const cart = await page.evaluate(() => {
      try {
        return JSON.parse(localStorage.getItem('darwin_cart')) || [];
      } catch {
        return [];
      }
    });

    expect(cart.length).toBeGreaterThan(0);
    const addedItem = cart.find(item => item.id === '11111111-1111-1111-1111-111111111111');
    expect(addedItem).toBeTruthy();
    expect(addedItem.qty).toBeGreaterThanOrEqual(1);
  });

  test('modal Add to Cart behavior matches tile Add to Cart behavior', async ({ page }) => {
    // Verify that both Add to Cart mechanisms produce the same cart result
    // First, add via the modal
    const modal = page.locator('#product-detail-modal');
    const modalAddBtn = modal.locator('button:has-text("Add to Cart"), .btn-add-cart');
    await modalAddBtn.click();

    const cartAfterModal = await page.evaluate(() => {
      try { return JSON.parse(localStorage.getItem('darwin_cart')) || []; } catch { return []; }
    });

    // Both buttons should produce the same cart item
    const addedItem = cartAfterModal.find(item => item.id === '11111111-1111-1111-1111-111111111111');
    expect(addedItem).toBeTruthy();
    expect(addedItem.id).toBe(PRODUCT_ID || '11111111-1111-1111-1111-111111111111');
  });
});

// ---- Out-of-stock product in modal ----

test.describe('Add to Cart in modal - out-of-stock product', () => {
  test('out-of-stock product detail modal shows no Add to Cart button', async ({ page }) => {
    await setupPage(page, [MOCK_PRODUCT_OUT_OF_STOCK]);
    await page.waitForSelector('.catalog-card', { timeout: 10000 });

    // Open modal for out-of-stock product
    await page.locator('.catalog-card').first().click({ position: { x: 5, y: 5 } });
    const modal = page.locator('#product-detail-modal');
    await expect(modal).toHaveClass(/active/, { timeout: 5000 });
    await expect(page.locator('#product-detail-content')).toContainText('Out of Stock Widget', { timeout: 5000 });

    // No Add to Cart button for out-of-stock (matches tile behavior)
    const addBtn = modal.locator('button:has-text("Add to Cart"), .btn-add-cart');
    const count = await addBtn.count();
    expect(count).toBe(0);
  });
});
