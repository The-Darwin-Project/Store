
const { test, expect } = require('@playwright/test');

test('Verify checkout flow', async ({ page }) => {
  // 1. Go to the store page
  // Assuming the app is running on localhost:8000 or similar. 
  // In the QE environment, we might verify against the deployed URL or localhost if running locally.
  // We'll use the environment variable or default to localhost.
  const baseURL = process.env.BASE_URL || 'http://localhost:8000';
  await page.goto(baseURL);

  // 2. Wait for products to load
  await expect(page.locator('.product-card')).toBeVisible();

  // 3. Add a product to cart
  // Assuming there is an "Add to Cart" button
  const addToCartBtn = page.locator('button:has-text("Add to Cart")').first();
  await addToCartBtn.click();

  // 4. Verify cart updates (optional, but good)
  // Assuming there's a cart counter or similar
  
  // 5. Click Checkout
  // The plan says "Update src/app/static/index.html to implement the checkout() function"
  // and "Update src/app/static/index.html to attach the checkout() function to the checkout button"
  const checkoutBtn = page.locator('button:has-text("Checkout")');
  await expect(checkoutBtn).toBeVisible();
  await checkoutBtn.click();

  // 6. Verify Success
  // The plan says "handle success (clear cart, show confirmation)"
  // We expect a success message or alert.
  // Since we can't easily capture window.alert in headless sometimes without listener, 
  // checking for a UI element is better.
  // The plan says "add the order success modal". So we look for a modal or success text.
  await expect(page.locator('text=Order placed successfully')).toBeVisible();

});
