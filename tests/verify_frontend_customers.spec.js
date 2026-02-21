const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

test.describe('Darwin Store Customer Feature', () => {
  const MOCK_CUSTOMER_ID = 'cust-123';
  const MOCK_ORDER_ID = 'ord-456';
  const MOCK_PRODUCT_ID = 'prod-789';

  test.beforeEach(async ({ page }) => {
    // State
    const customers = [{
      id: MOCK_CUSTOMER_ID,
      name: 'Existing Customer',
      email: 'existing@example.com',
      created_at: '2023-01-01T00:00:00'
    }];

    // 1. Mock /products
    await page.route('**/products', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([{
          id: MOCK_PRODUCT_ID,
          name: 'Test Product',
          sku: 'TEST-001',
          price: 10.00,
          stock: 10,
          image_data: null
        }])
      });
    });

    // 2. Mock /customers GET and POST
    await page.route('**/customers', async route => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(customers)
        });
      } else if (route.request().method() === 'POST') {
        const data = route.request().postDataJSON();
        const newCustomer = {
            id: 'new-cust-id',
            name: data.name,
            email: data.email,
            created_at: new Date().toISOString()
        };
        customers.push(newCustomer);
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(newCustomer)
        });
      }
    });

    // 3. Mock /orders
    await page.route('**/orders', async route => {
      if (route.request().method() === 'POST') {
        const data = route.request().postDataJSON();
        if (!data.customer_id) {
           await route.fulfill({ status: 422, body: JSON.stringify({ detail: 'Missing customer_id' }) });
           return;
        }
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            id: MOCK_ORDER_ID,
            total_amount: 10.00,
            status: 'confirmed',
            items: data.items,
            customer_id: data.customer_id,
            created_at: new Date().toISOString()
          })
        });
      } else {
        await route.fulfill({ status: 200, body: '[]' });
      }
    });

    // 4. Mock /customers/{id}/orders
    await page.route(`**/customers/${MOCK_CUSTOMER_ID}/orders`, async route => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify([{
                id: MOCK_ORDER_ID,
                total_amount: 10.00,
                status: 'confirmed',
                created_at: '2023-01-02T00:00:00',
                customer_id: MOCK_CUSTOMER_ID
            }])
        });
    });

    // 5. Mock DELETE /customers/{id}/orders/{order_id}
    await page.route(`**/customers/${MOCK_CUSTOMER_ID}/orders/${MOCK_ORDER_ID}`, async route => {
        if (route.request().method() === 'DELETE') {
            await route.fulfill({ status: 204 });
        }
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

  test('should verify Customers tab exists and lists customers', async ({ page }) => {
    await page.click('#customers-tab');
    await expect(page.locator('#customer-list')).toContainText('Existing Customer');
    await expect(page.locator('#customer-list')).toContainText('existing@example.com');
  });

  test('should create a new customer via Customers tab', async ({ page }) => {
    await page.click('#customers-tab');
    
    await page.fill('#cust-name', 'New Tab Customer');
    await page.fill('#cust-email', 'tab@example.com');
    await page.click('button:has-text("Add Customer")');
    
    // Verify log message or reload (we mocked POST but list reload depends on subsequent GET)
    // The mocked GET only returns the initial customer. 
    // In a real app, the list would update. 
    // But our log shows success.
    await expect(page.locator('#log')).toContainText('Created customer: New Tab Customer');
  });

  test('should display orders for selected customer and allow detach', async ({ page }) => {
    await page.click('#customers-tab');
    
    // Select the customer
    await page.click('.customer-list-item');
    
    // Check orders table
    const orderRow = page.locator('#customer-orders-table tr').first();
    await expect(orderRow).toContainText(MOCK_ORDER_ID.substring(0, 8));
    
    // Click detach
    // We need to handle the dialog? No, it's just a button in this implementation (no confirm modal for detach based on code reading)
    // Wait, let's check index.html again. 
    // <button class="small danger" onclick="detachOrder('${customerId}', '${o.id}')">Detach</button>
    // No modal.
    
    await orderRow.locator('button:has-text("Detach")').click();
    
    await expect(page.locator('#log')).toContainText(`Order ${MOCK_ORDER_ID.substring(0, 8)}... detached`);
  });

  test('should enforce customer selection during checkout', async ({ page }) => {
    // 1. Add item to cart
    await page.click('button:has-text("Add to Cart")');
    
    // 2. Go to Cart
    await page.click('#cart-tab');
    
    // 3. Try checkout without customer
    // Ensure dropdown is empty or default
    await page.selectOption('#checkout-customer', ''); 
    await page.click('#checkout-btn');
    
    // Should see error in log
    await expect(page.locator('#log')).toContainText('Please select a customer');
    
    // 4. Select customer and checkout
    await page.selectOption('#checkout-customer', MOCK_CUSTOMER_ID);
    await page.click('#checkout-btn');
    
    // Success modal should appear
    await expect(page.locator('#order-success-modal')).toHaveClass(/active/);
    await expect(page.locator('#order-details')).toContainText(MOCK_ORDER_ID);
  });

  test('should allow creating new customer during checkout', async ({ page }) => {
    // 1. Add to cart
    await page.click('button:has-text("Add to Cart")');
    await page.click('#cart-tab');
    
    // 2. Open inline form
    await page.click('button:has-text("New Customer")');
    await expect(page.locator('#inline-new-customer')).toBeVisible();
    
    // 3. Create customer
    await page.fill('#new-cust-name', 'Inline Customer');
    await page.fill('#new-cust-email', 'inline@example.com');
    await page.click('button:has-text("Create")'); // Inside the inline form
    
    // 4. Verify log and selection
    await expect(page.locator('#log')).toContainText('Created customer: Inline Customer');
    // The dropdown should now be set to the new customer (id: new-cust-id)
    await expect(page.locator('#checkout-customer')).toHaveValue('new-cust-id');
  });
});
