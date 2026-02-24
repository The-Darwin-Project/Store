// Store/tests/verify_reviews_ui.spec.js
// @ai-rules:
// 1. [Pattern]: Self-contained with route mocking (no server needed).
// 2. [Constraint]: Tests product detail modal, star ratings, review form, and orders integration.
const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const PRODUCT_ID = '11111111-1111-1111-1111-111111111111';
const CUSTOMER_ID = '22222222-2222-2222-2222-222222222222';

test.describe('Product Reviews and Detail View', () => {
  test.beforeEach(async ({ page }) => {
    // Mock /products list
    await page.route('**/products', async route => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: PRODUCT_ID,
              name: 'Test Widget',
              price: 29.99,
              stock: 10,
              sku: 'TW-001',
              image_data: null,
              description: 'A great test widget',
              supplier_id: null,
              reorder_threshold: 10
            }
          ])
        });
      } else {
        await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
      }
    });

    // Mock /products/{id} GET
    await page.route(`**/products/${PRODUCT_ID}`, async route => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: PRODUCT_ID,
            name: 'Test Widget',
            price: 29.99,
            stock: 10,
            sku: 'TW-001',
            image_data: null,
            description: 'A great test widget',
            supplier_id: null,
            reorder_threshold: 10
          })
        });
      } else {
        await route.fallback();
      }
    });

    // Mock average-rating
    await page.route(`**/products/${PRODUCT_ID}/average-rating`, async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ product_id: PRODUCT_ID, average_rating: 4.2, review_count: 5 })
      });
    });

    // Mock reviews GET
    await page.route(`**/products/${PRODUCT_ID}/reviews`, async route => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: 'r1',
              product_id: PRODUCT_ID,
              customer_id: CUSTOMER_ID,
              customer_name: 'Alice',
              rating: 5,
              comment: 'Excellent product!',
              created_at: '2026-02-20T10:00:00'
            }
          ])
        });
      } else if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'r2',
            product_id: PRODUCT_ID,
            customer_id: CUSTOMER_ID,
            customer_name: 'Alice',
            rating: 4,
            comment: 'Nice',
            created_at: '2026-02-24T10:00:00'
          })
        });
      } else {
        await route.fallback();
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

    // Navigate to storefront
    const indexPath = path.resolve(__dirname, '..', 'src', 'app', 'static', 'index.html');
    await page.goto('file://' + indexPath);
    await page.waitForTimeout(500);
  });

  test('product tiles show star ratings', async ({ page }) => {
    const ratingEl = page.locator('.catalog-card .card-rating');
    await expect(ratingEl.first()).toBeVisible();
    // Should contain star characters
    const text = await ratingEl.first().textContent();
    expect(text).toContain('(5)');
  });

  test('clicking product tile opens detail modal', async ({ page }) => {
    // Click on the product card (not the add to cart button)
    await page.locator('.catalog-card').first().click();

    // Modal should be visible
    const modal = page.locator('#product-detail-modal');
    await expect(modal).toHaveClass(/active/);

    // Should show product name
    const content = page.locator('#product-detail-content');
    await expect(content).toContainText('Test Widget');
    await expect(content).toContainText('$29.99');

    // Should show reviews section
    await expect(content).toContainText('Customer Reviews');
    await expect(content).toContainText('Alice');
    await expect(content).toContainText('Excellent product!');
  });

  test('review form is present in modal', async ({ page }) => {
    await page.locator('.catalog-card').first().click();
    const modal = page.locator('#product-detail-modal');
    await expect(modal).toHaveClass(/active/);

    // Should show review form elements
    await expect(page.locator('#review-customer')).toBeVisible();
    await expect(page.locator('#star-picker')).toBeVisible();
    await expect(page.locator('#review-comment')).toBeVisible();
  });

  test('delivered orders show Review Products button', async ({ page }) => {
    // Switch to orders tab
    await page.click('#orders-tab');
    await page.waitForTimeout(300);

    // Should see "Review Products" button
    const reviewBtn = page.locator('button', { hasText: 'Review Products' });
    await expect(reviewBtn.first()).toBeVisible();
  });
});
