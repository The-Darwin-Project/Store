
const { test, expect } = require('@playwright/test');

test('Verify Order History UI', async ({ page }) => {
  // Mock Data
  const mockProducts = [
    {
      id: "prod-1",
      name: "Test Item 1",
      price: 10.0,
      stock: 5,
      sku: "TEST-001",
      description: "A test item",
      image_data: null
    }
  ];

  const mockOrders = [
    {
      id: "order-123",
      created_at: new Date().toISOString(), // Today
      total_amount: 20.0,
      status: "confirmed",
      items: [
        {
          id: "item-1",
          order_id: "order-123",
          product_id: "prod-1",
          quantity: 2,
          price_at_purchase: 10.0
        }
      ]
    },
    {
      id: "order-456",
      created_at: new Date(Date.now() - 86400000).toISOString(), // Yesterday
      total_amount: 100.0,
      status: "shipped",
      items: [
        {
          id: "item-2",
          order_id: "order-456",
          product_id: "prod-1",
          quantity: 10,
          price_at_purchase: 10.0
        }
      ]
    }
  ];

  // Intercept API calls
  await page.route('**/products', async route => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ json: mockProducts });
    } else {
      await route.continue();
    }
  });

  await page.route('**/orders', async route => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ json: mockOrders });
    } else {
      await route.continue();
    }
  });

  // Navigate to the static page
  await page.goto('http://localhost:8081/index.html');

  // 1. Verify "Orders" link exists
  // The nav item is a button with role="tab"
  const ordersLink = page.getByRole('tab', { name: 'Orders' });
  await expect(ordersLink).toBeVisible();

  // 2. Click "Orders"
  await ordersLink.click();

  // 3. Verify Orders View is visible
  // The implementation uses #orders
  const ordersView = page.locator('#orders');
  await expect(ordersView).toBeVisible();

  // 4. Verify Order Data
  // Check for Order ID, Date, Total, Status
  // Note: The UI truncates the ID to 8 chars.
  await expect(ordersView).toContainText('order-12');
  await expect(ordersView).toContainText('confirmed');
  await expect(ordersView).toContainText('$20.00'); // Assuming currency formatting
  
  await expect(ordersView).toContainText('order-45');
  await expect(ordersView).toContainText('shipped');

  await expect(ordersView).toContainText('$100.00');

  // 5. Check Items (The current UI only shows summary: Date, ID, Total, Status)
  // We verify that the rows are present (implied by content checks above).
  // Ideally, we'd check row count.
  await expect(page.locator('#orders-table tr')).toHaveCount(2); // 2 orders
 

});
