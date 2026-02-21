const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

test.describe('Shopping Cart Feature', () => {
    // Mock product data
    const mockProducts = [
        {
            id: 'p1',
            name: 'Test Product 1',
            sku: 'TP-001',
            price: 10.00,
            stock: 100,
            image_data: null,
            description: 'Description 1'
        },
        {
            id: 'p2',
            name: 'Test Product 2',
            sku: 'TP-002',
            price: 20.50,
            stock: 5,
            image_data: null,
            description: 'Description 2'
        },
        {
            id: 'p3',
            name: 'Out of Stock Product',
            sku: 'TP-003',
            price: 30.00,
            stock: 0,
            image_data: null,
            description: 'Description 3'
        }
    ];

    test.beforeEach(async ({ page }) => {
        // Intercept API call to return mock data
        await page.route('**/products', async route => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify(mockProducts)
            });
        });

        // Mock the HTML file serving
        const htmlPath = path.resolve(__dirname, '../src/app/static/index.html');
        const htmlContent = fs.readFileSync(htmlPath, 'utf8');

        await page.route('http://localhost/', async route => {
            await route.fulfill({
                status: 200,
                contentType: 'text/html',
                body: htmlContent
            });
        });

        // Clear local storage before each test (need to be done after goto usually, but here we can do it via init script or evaluate)
        // Actually, Playwright has a new context for each test, so localStorage is empty by default.
        
        await page.goto('http://localhost/');
    });

    test('should display cart icon and initially be empty', async ({ page }) => {
        // Check for header icon
        const cartIcon = page.locator('.cart-icon-wrapper');
        await expect(cartIcon).toBeVisible();

        // Check badge is hidden or 0
        const badge = page.locator('#cart-badge');
        await expect(badge).toHaveText('0');
        // The implementation toggles 'hidden' class if count is 0
        await expect(badge).toHaveClass(/hidden/);

        // Switch to Cart tab
        await page.click('#cart-tab');
        
        // Check empty state
        const emptyState = page.locator('#cart-table .empty-state');
        await expect(emptyState).toBeVisible();
        await expect(emptyState).toHaveText('Your cart is empty.');
        
        // Check total is empty
        const total = page.locator('#cart-total');
        await expect(total).toHaveText('');
    });

    test('should add items to cart and update badge', async ({ page }) => {
        // Go to Catalog
        await page.click('#catalog-tab');

        // Add Product 1 to cart
        const firstProductCard = page.locator('.catalog-card').filter({ hasText: 'Test Product 1' });
        await firstProductCard.getByRole('button', { name: 'Add to Cart' }).click();

        // Check badge update
        const badge = page.locator('#cart-badge');
        await expect(badge).toBeVisible(); // Should be visible now
        await expect(badge).not.toHaveClass(/hidden/);
        await expect(badge).toHaveText('1');

        // Add Product 2 to cart
        const secondProductCard = page.locator('.catalog-card').filter({ hasText: 'Test Product 2' });
        await secondProductCard.getByRole('button', { name: 'Add to Cart' }).click();

        // Check badge update
        await expect(badge).toHaveText('2');

        // Add Product 1 again (qty update)
        await firstProductCard.getByRole('button', { name: 'Add to Cart' }).click();
        await expect(badge).toHaveText('3'); // Total items count (1+1+1)
    });

    test('should verify cart contents and calculations', async ({ page }) => {
        // Add items first
        await page.click('#catalog-tab');
        const firstProductCard = page.locator('.catalog-card').filter({ hasText: 'Test Product 1' }); // Price 10.00
        const secondProductCard = page.locator('.catalog-card').filter({ hasText: 'Test Product 2' }); // Price 20.50

        await firstProductCard.getByRole('button', { name: 'Add to Cart' }).click(); // 1x P1
        await firstProductCard.getByRole('button', { name: 'Add to Cart' }).click(); // 2x P1
        await secondProductCard.getByRole('button', { name: 'Add to Cart' }).click(); // 1x P2

        // Go to Cart View
        await page.click('#cart-tab');

        // Verify rows
        const rows = page.locator('#cart-table tr');
        await expect(rows).toHaveCount(2);

        // Row 1: Test Product 1
        const row1 = rows.first();
        await expect(row1).toContainText('Test Product 1');
        await expect(row1.locator('td.price').first()).toHaveText('$10.00'); // Unit Price
        await expect(row1.locator('.cart-qty-controls span')).toHaveText('2'); // Qty
        await expect(row1.locator('td.price').last()).toHaveText('$20.00'); // Subtotal

        // Row 2: Test Product 2
        const row2 = rows.last();
        await expect(row2).toContainText('Test Product 2');
        await expect(row2.locator('td.price').first()).toHaveText('$20.50');
        await expect(row2.locator('.cart-qty-controls span')).toHaveText('1');
        await expect(row2.locator('td.price').last()).toHaveText('$20.50');

        // Verify Grand Total
        // Total = 20.00 + 20.50 = 40.50
        const total = page.locator('#cart-total');
        await expect(total).toContainText('$40.50');
    });

    test('should update quantity in cart view', async ({ page }) => {
        // Add item
        await page.click('#catalog-tab');
        const firstProductCard = page.locator('.catalog-card').filter({ hasText: 'Test Product 1' });
        await firstProductCard.getByRole('button', { name: 'Add to Cart' }).click();

        // Go to Cart
        await page.click('#cart-tab');
        
        const row = page.locator('#cart-table tr').first();
        const qtyDisplay = row.locator('.cart-qty-controls span');
        const plusBtn = row.locator('button', { hasText: '+' });
        const minusBtn = row.locator('button', { hasText: '-' });
        const subtotal = row.locator('td.price').last();
        const grandTotal = page.locator('#cart-total');

        // Initial check
        await expect(qtyDisplay).toHaveText('1');
        await expect(subtotal).toHaveText('$10.00');
        await expect(grandTotal).toContainText('$10.00');

        // Increase quantity
        await plusBtn.click();
        await expect(qtyDisplay).toHaveText('2');
        await expect(subtotal).toHaveText('$20.00');
        await expect(grandTotal).toContainText('$20.00');
        await expect(page.locator('#cart-badge')).toHaveText('2');

        // Decrease quantity
        await minusBtn.click();
        await expect(qtyDisplay).toHaveText('1');
        await expect(subtotal).toHaveText('$10.00');
        await expect(grandTotal).toContainText('$10.00');
        await expect(page.locator('#cart-badge')).toHaveText('1');
    });

    test('should remove item when quantity goes to 0 or remove button clicked', async ({ page }) => {
         // Add item
         await page.click('#catalog-tab');
         const firstProductCard = page.locator('.catalog-card').filter({ hasText: 'Test Product 1' });
         await firstProductCard.getByRole('button', { name: 'Add to Cart' }).click();
 
         // Go to Cart
         await page.click('#cart-tab');
         const row = page.locator('#cart-table tr').first();
         const minusBtn = row.locator('button', { hasText: '-' });

         // Decrease to 0
         await minusBtn.click();
         
         // Cart should be empty
         await expect(page.locator('#cart-table .empty-state')).toBeVisible();
         await expect(page.locator('#cart-badge')).toHaveClass(/hidden/);

         // Add again to test "Remove" button
         await page.click('#catalog-tab');
         await firstProductCard.getByRole('button', { name: 'Add to Cart' }).click();
         await page.click('#cart-tab');
         
         // Click Remove
         await page.locator('button.danger', { hasText: 'Remove' }).click();
         await expect(page.locator('#cart-table .empty-state')).toBeVisible();
    });

    test('should persist cart in localStorage', async ({ page }) => {
        // Add item
        await page.click('#catalog-tab');
        const firstProductCard = page.locator('.catalog-card').filter({ hasText: 'Test Product 1' });
        await firstProductCard.getByRole('button', { name: 'Add to Cart' }).click();
        
        // Verify badge
        await expect(page.locator('#cart-badge')).toHaveText('1');

        // Reload page
        await page.reload();

        // Verify state persisted
        await expect(page.locator('#cart-badge')).toHaveText('1');
        
        await page.click('#cart-tab');
        await expect(page.locator('#cart-table tr')).toHaveCount(1);
        await expect(page.locator('#cart-table tr').first()).toContainText('Test Product 1');
    });
});
