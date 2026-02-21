// tests/verify_suppliers_ui.spec.js
// @ai-rules: Playwright UI tests

const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

test.describe('Supplier Management UI', () => {
    test.beforeEach(async ({ page }) => {
        // Load the HTML file
        const htmlPath = path.resolve(__dirname, '../src/app/static/index.html');
        const htmlContent = fs.readFileSync(htmlPath, 'utf8');

        await page.route('http://localhost/', async route => {
            await route.fulfill({
                status: 200,
                contentType: 'text/html',
                body: htmlContent
            });
        });

        // Mock API responses
        await page.route('**/products', async route => {
            if (route.request().method() === 'GET') {
                await route.fulfill({
                    status: 200,
                    contentType: 'application/json',
                    body: JSON.stringify([{
                        id: 'prod-1',
                        name: 'Test Product',
                        sku: 'SKU-1',
                        price: 10,
                        stock: 5,
                        supplier_id: 'supp-1',
                        reorder_threshold: 10
                    }])
                });
            }
        });

        await page.route('**/suppliers', async route => {
            if (route.request().method() === 'GET') {
                await route.fulfill({
                    status: 200,
                    contentType: 'application/json',
                    body: JSON.stringify([{
                        id: 'supp-1',
                        name: 'Test Supplier',
                        contact_email: 'test@example.com',
                        phone: '1234567890',
                        low_stock_count: 1
                    }])
                });
            } else if (route.request().method() === 'POST') {
                await route.fulfill({
                    status: 201,
                    contentType: 'application/json',
                    body: JSON.stringify({
                        id: 'supp-new',
                        name: 'New Supplier',
                        contact_email: '',
                        phone: ''
                    })
                });
            }
        });
        
        await page.route('**/customers', async route => {
            await route.fulfill({ status: 200, body: '[]' });
        });
        await page.route('**/orders', async route => {
            await route.fulfill({ status: 200, body: '[]' });
        });

        await page.goto('http://localhost/');

        // Trigger initialization
        await page.evaluate(() => {
            loadSuppliers().then(() => loadProducts());
        });
    });

    test('should display suppliers tab and add supplier', async ({ page }) => {
        // Click suppliers tab
        await page.click('#suppliers-tab');
        await expect(page.locator('#suppliers')).toHaveClass(/active/);

        // Check if supplier is listed
        const supplierList = page.locator('#supplier-list');
        await expect(supplierList).toContainText('Test Supplier');
        await expect(supplierList).toContainText('1 low stock');

        // Add a new supplier
        await page.fill('#supp-name', 'New Supplier');
        await page.click('#add-supplier-form button[type="submit"]');

        // Check if the success log is displayed
        await expect(page.locator('#log')).toContainText('Added supplier: New Supplier');
    });

    test('should display supplier in add product dropdown', async ({ page }) => {
        await page.click('#inventory-tab');
        
        const dropdown = page.locator('#add-supplier');
        await expect(dropdown).toContainText('Test Supplier');
    });

    test('should highlight low stock supplier in inventory', async ({ page }) => {
        await page.click('#inventory-tab');
        
        // Wait for inventory to render
        await page.waitForSelector('#product-table tr[data-id="prod-1"]');
        
        // Check if supplier cell has the .supplier-reorder class
        const supplierCell = page.locator('#product-table tr[data-id="prod-1"] span.supplier-reorder');
        await expect(supplierCell).toBeVisible();
        await expect(supplierCell).toContainText('Test Supplier');
    });
});
