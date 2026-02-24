const { test, expect } = require('@playwright/test');

test.describe('Discount Coupon UI', () => {

  test('Coupon UI elements exist', async ({ page }) => {
    // Navigate to the dashboard where the cart is
    await page.goto('/');

    // Wait for page load
    await page.waitForSelector('.product-card');

    // Add a product to the cart
    await page.click('.product-card button.primary');
    
    // Switch to Cart tab
    await page.click('button[onclick="switchTab('cart')"]');

    // Wait for the cart table
    await page.waitForSelector('#cart-items');

    // Verify coupon section is visible (should be un-hidden when cart has items)
    const couponSection = page.locator('#coupon-section');
    await expect(couponSection).toBeVisible();

    const couponInput = page.locator('#coupon-input');
    await expect(couponInput).toBeVisible();
    await expect(couponInput).toHaveAttribute('placeholder', 'Enter coupon code');

    const applyBtn = page.locator('button[onclick="applyCoupon()"]');
    await expect(applyBtn).toBeVisible();
    await expect(applyBtn).toHaveText('Apply');
  });

  test('Shows error for invalid coupon', async ({ page }) => {
    await page.route('/coupons/validate', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          valid: false,
          error: 'Coupon is not active'
        })
      });
    });

    await page.goto('/');
    await page.waitForSelector('.product-card');
    await page.click('.product-card button.primary');
    await page.click('button[onclick="switchTab('cart')"]');
    await page.waitForSelector('#cart-items');

    await page.fill('#coupon-input', 'INVALID10');
    await page.click('button[onclick="applyCoupon()"]');

    const resultMsg = page.locator('#coupon-result .coupon-error');
    await expect(resultMsg).toBeVisible();
    await expect(resultMsg).toContainText('Coupon is not active');
  });

  test('Shows success and calculates total correctly for valid coupon', async ({ page }) => {
    await page.route('/coupons/validate', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          valid: true,
          coupon: {
            code: 'VALID20',
            discount_type: 'percentage',
            discount_value: 20,
            min_order_amount: 0,
            max_uses: 0,
            current_uses: 0,
            is_active: true
          },
          discount_amount: 19.99, // assuming a 99.99 item * 20%
          final_total: 79.99
        })
      });
    });

    await page.goto('/');
    await page.waitForSelector('.product-card');
    await page.click('.product-card button.primary'); // Add one item
    await page.click('button[onclick="switchTab('cart')"]');
    await page.waitForSelector('#cart-items');

    await page.fill('#coupon-input', 'VALID20');
    await page.click('button[onclick="applyCoupon()"]');

    const resultMsg = page.locator('#coupon-result .coupon-success');
    await expect(resultMsg).toBeVisible();
    await expect(resultMsg).toContainText('Coupon "VALID20" applied');

    // The cart total div should show the discount line
    const totalDiv = page.locator('#cart-total');
    await expect(totalDiv).toContainText('Discount (VALID20): -$19.99');
    
    // Ensure the checkout button is still clickable
    const checkoutBtn = page.locator('button[onclick="checkout()"]');
    await expect(checkoutBtn).toBeVisible();
  });
});
