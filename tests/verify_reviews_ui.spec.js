// Store/tests/verify_reviews_ui.spec.js
// @ai-rules:
// 1. [Pattern]: Self-contained with route mocking via http://localhost (no server needed).
// 2. [Constraint]: Tests product detail modal, star ratings, review form, and orders integration.
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

const MOCK_RATING = { product_id: PRODUCT_ID, average_rating: 4.2, review_count: 5 };

const MOCK_REVIEWS = [
  {
    id: 'r1',
    product_id: PRODUCT_ID,
    customer_id: CUSTOMER_ID,
    customer_name: 'Alice',
    rating: 5,
    comment: 'Excellent product!',
    created_at: '2026-02-20T10:00:00'
  }
];

test.describe('Product Reviews and Detail View', () => {
  test.beforeEach(async ({ page }) => {
    // Mock average-rating (must be before /products to take priority)
    await page.route(`**/products/${PRODUCT_ID}/average-rating`, async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_RATING)
      });
    });

    // Mock reviews GET/POST
    await page.route(`**/products/${PRODUCT_ID}/reviews`, async route => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'r2', product_id: PRODUCT_ID, customer_id: CUSTOMER_ID,
            customer_name: 'Alice', rating: 4, comment: 'Nice',
            created_at: '2026-02-24T10:00:00'
          })
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_REVIEWS)
        });
      }
    });

    // Mock single product GET
    await page.route(`**/products/${PRODUCT_ID}`, async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_PRODUCT)
      });
    });

    // Mock /products list
    await page.route('**/products', async route => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([MOCK_PRODUCT])
        });
      } else {
        await route.continue();
      }
    });

    // Mock /customers
    await page.route('**/customers', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: CUSTOMER_ID, name: 'Alice', email: 'alice@example.com', created_at: new Date().toISOString() }
        ])
      });
    });

    // Mock /orders
    await page.route('**/orders', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'order-1',
            created_at: new Date().toISOString(),
            total_amount: 29.99,
            status: 'delivered',
            customer_id: CUSTOMER_ID,
            customer_name: 'Alice',
            invoice_id: 'inv-1',
            items: [{ id: 'oi-1', order_id: 'order-1', product_id: PRODUCT_ID, quantity: 1, price_at_purchase: 29.99, product_name: 'Test Widget' }]
          }
        ])
      });
    });

    // Serve index.html via http://localhost/ (matches established test pattern)
    const htmlPath = path.resolve(__dirname, '..', 'src', 'app', 'static', 'index.html');
    const htmlContent = fs.readFileSync(htmlPath, 'utf8');

    await page.route('http://localhost/', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'text/html',
        body: htmlContent
      });
    });

    // Serve shared.css
    const cssPath = path.resolve(__dirname, '..', 'src', 'app', 'static', 'shared.css');
    const cssContent = fs.readFileSync(cssPath, 'utf8');

    await page.route('**/static/shared.css', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'text/css',
        body: cssContent
      });
    });

    await page.goto('http://localhost/');
    await page.waitForSelector('.catalog-card', { timeout: 10000 });
  });

  test('product tiles show star ratings', async ({ page }) => {
    const ratingEl = page.locator('.catalog-card .card-rating');
    await expect(ratingEl.first()).toBeVisible();
    const text = await ratingEl.first().textContent();
    expect(text).toContain('(5)');
  });

  test('clicking product tile opens detail modal', async ({ page }) => {
    await page.locator('.catalog-card').first().click();

    const modal = page.locator('#product-detail-modal');
    await expect(modal).toHaveClass(/active/);

    const content = page.locator('#product-detail-content');
    await expect(content).toContainText('Test Widget');
    await expect(content).toContainText('$29.99');
    await expect(content).toContainText('Customer Reviews');
    await expect(content).toContainText('Alice');
    await expect(content).toContainText('Excellent product!');
  });

  test('review form is present in modal', async ({ page }) => {
    await page.locator('.catalog-card').first().click();
    const modal = page.locator('#product-detail-modal');
    await expect(modal).toHaveClass(/active/);

    await expect(page.locator('#review-customer')).toBeVisible();
    await expect(page.locator('#star-picker')).toBeVisible();
    await expect(page.locator('#review-comment')).toBeVisible();
  });

  test('delivered orders show Review Products button', async ({ page }) => {
    await page.click('#orders-tab');
    await page.waitForSelector('.order-row', { timeout: 10000 });

    const reviewBtn = page.locator('button', { hasText: 'Review Products' });
    await expect(reviewBtn.first()).toBeVisible();
  });
});
