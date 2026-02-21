
const { test, expect } = require('@playwright/test');

test('Verify Checkout UI Flow with Mocked Backend', async ({ page }) => {
  // Mock Data
  const mockProducts = [
    {
      id: "prod-1",
      name: "Test Item",
      price: 10.0,
      stock: 5,
      sku: "TEST-001",
      description: "A test item",
      image_data: null
    }
  ];

  const mockOrderResponse = {
    id: "order-123",
    created_at: new Date().toISOString(),
    total_amount: 20.0,
    status: "pending",
    items: [
      {
        id: "item-1",
        order_id: "order-123",
        product_id: "prod-1",
        quantity: 2,
        price_at_purchase: 10.0
      }
    ]
  };

  // Intercept API calls
  await page.route('**/products', async route => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ json: mockProducts });
    } else {
      await route.continue();
    }
  });

  await page.route('**/orders', async route => {
    if (route.request().method() === 'POST') {
      // Verify payload
      const postData = route.request().postDataJSON();
      expect(postData.items[0].product_id).toBe("prod-1");
      expect(postData.items[0].quantity).toBe(2);
      
      await route.fulfill({ json: mockOrderResponse, status: 201 });
    } else {
      await route.continue();
    }
  });

  // Navigate to the static page
  await page.goto('http://localhost:8081/index.html');

  // 1. Verify Product is displayed
  await expect(page.locator('.catalog-card')).toBeVisible();
  await expect(page.locator('.catalog-card h3:has-text("Test Item")')).toBeVisible();
  await expect(page.locator('.catalog-card .card-price:has-text("$10.00")')).toBeVisible();

  // 2. Add to Cart (Click twice to test quantity)
  const addBtn = page.locator('button:has-text("Add to Cart")');
  await addBtn.click();
  await addBtn.click();

  // Verify Cart Badge
  await expect(page.locator('#cart-badge')).toHaveText('2');

  // 3. Switch to Cart Tab
  await page.click('#cart-tab');
  
  // Verify Cart Content
  await expect(page.locator('#cart-table')).toContainText('Test Item');
  await expect(page.locator('#cart-total')).toContainText('$20.00');
  
  // 4. Click Checkout
  const checkoutBtn = page.locator('#checkout-btn');
  await expect(checkoutBtn).toBeVisible();
  await checkoutBtn.click();

  // 5. Verify Success Modal
  const modal = page.locator('#order-success-modal');
  await expect(modal).toBeVisible();
  await expect(modal).toContainText('Order Confirmed');
  await expect(modal).toContainText('Total: $20.00');

  // 6. Close Modal and verify cart cleared (mocked logic in frontend handles clearing)
  await page.click('button:has-text("Continue Shopping")');
  await expect(modal).not.toBeVisible();
  
  // Verify badge is gone/zero
  await expect(page.locator('#cart-badge')).toBeHidden();
  
});
