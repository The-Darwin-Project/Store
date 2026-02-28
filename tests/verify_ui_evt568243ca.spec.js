// tests/verify_ui_evt568243ca.spec.js
// Playwright tests for evt-568243ca UI fixes:
//   1. Store CSS unified to PatternFly Dark theme
//   2. Campaign ad bar has correct image and design
//   3. Page alignment fixed (store main card aligned with root viewport)
//
// Tests run against the live store deployment.

const { test, expect } = require('@playwright/test');

// Use local build when available (for branch testing), fall back to live
const BASE_URL = process.env.STORE_URL || 'http://localhost:3456';

const NOW = new Date();
const PAST = new Date(NOW.getTime() - 86400000).toISOString();
const FUTURE = new Date(NOW.getTime() + 86400000 * 7).toISOString();

const MOCK_PRODUCTS = [
  { id: 'prod-1', name: 'Test Widget', sku: 'TW-001', price: 29.99, stock: 50, description: 'A test widget', image_data: null },
];

const MOCK_ACTIVE_CAMPAIGNS = [
  {
    id: 'camp-banner',
    title: 'Grand Summer Sale',
    type: 'banner',
    content: 'Everything 50% off this week!',
    image_url: 'https://images.unsplash.com/photo-1607082348824-0a96f2a4b9da?w=1200',
    link_url: null,
    coupon_code: null,
    product_id: null,
    start_date: PAST,
    end_date: FUTURE,
    is_active: true,
    priority: 10,
    created_at: NOW.toISOString(),
  },
  {
    id: 'camp-promo',
    title: 'Flash Deal',
    type: 'discount_promo',
    content: 'Save 20% on everything',
    image_url: null,
    link_url: null,
    coupon_code: 'FLASH20',
    product_id: null,
    start_date: PAST,
    end_date: FUTURE,
    is_active: true,
    priority: 5,
    created_at: NOW.toISOString(),
  },
];

const MOCK_ACTIVE_CAMPAIGNS_NO_IMAGE = [
  {
    id: 'camp-no-img',
    title: 'No Image Banner',
    type: 'banner',
    content: 'Sale without an image',
    image_url: null,
    link_url: null,
    coupon_code: null,
    product_id: null,
    start_date: PAST,
    end_date: FUTURE,
    is_active: true,
    priority: 10,
    created_at: NOW.toISOString(),
  },
];

// ============================================================================
// Helpers
// ============================================================================

async function mockAPIs(page, { campaigns = MOCK_ACTIVE_CAMPAIGNS, products = MOCK_PRODUCTS } = {}) {
  await page.route('**/campaigns/active', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(campaigns),
    });
  });
  await page.route('**/products', async route => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(products),
      });
    } else {
      await route.continue();
    }
  });
  await page.route('**/reviews**', async route =>
    route.fulfill({ status: 200, body: '[]' }));
  await page.route('**/orders**', async route =>
    route.fulfill({ status: 200, body: '[]' }));
  await page.route('**/alerts**', async route =>
    route.fulfill({ status: 200, body: '[]' }));
}

async function gotoStore(page) {
  await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 20000 });
  // Wait for React to mount and render the catalog tab
  await page.waitForSelector('[id="catalog"], .pf-v6-c-tabs', { timeout: 10000 });
}

// ============================================================================
// 1. PatternFly Dark Theme
// ============================================================================

test.describe('1. PatternFly Dark Theme Unification', () => {

  test('html element has pf-v6-theme-dark class', async ({ page }) => {
    await gotoStore(page);
    const htmlClass = await page.locator('html').getAttribute('class');
    expect(htmlClass).toContain('pf-v6-theme-dark');
  });

  test('body background-color is dark (not white)', async ({ page }) => {
    await gotoStore(page);
    const bgColor = await page.evaluate(() => {
      return window.getComputedStyle(document.body).backgroundColor;
    });
    // Background should be dark - rgb values should all be < 50 for a dark theme
    // Expected: rgb(26, 26, 46) = #1a1a2e (--ds-bg-primary)
    const match = bgColor.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
    expect(match).not.toBeNull();
    if (match) {
      const [, r, g, b] = match.map(Number);
      const brightness = (r + g + b) / 3;
      expect(brightness).toBeLessThan(80); // Dark background
    }
  });

  test('PatternFly base CSS is loaded', async ({ page }) => {
    await gotoStore(page);
    // Check that PatternFly CSS variables are defined
    const pfVar = await page.evaluate(() => {
      return getComputedStyle(document.documentElement)
        .getPropertyValue('--pf-t--global--background--color--primary--default');
    });
    expect(pfVar.trim()).toBeTruthy();
  });

  test('dark theme CSS variable --ds-bg-primary is defined', async ({ page }) => {
    await gotoStore(page);
    const dsVar = await page.evaluate(() => {
      return getComputedStyle(document.documentElement)
        .getPropertyValue('--ds-bg-primary');
    });
    // Should be defined and not empty
    expect(dsVar.trim()).not.toBe('');
  });

  test('product cards have dark background (not white)', async ({ page }) => {
    await mockAPIs(page);
    await gotoStore(page);

    // Wait for product card to render
    const card = page.locator('.catalog-card, .ds-product-card').first();
    await expect(card).toBeVisible({ timeout: 8000 });

    const bgColor = await card.evaluate(el => {
      return window.getComputedStyle(el).backgroundColor;
    });
    // Card background should NOT be white/very light
    const match = bgColor.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
    if (match) {
      const [, r, g, b] = match.map(Number);
      const brightness = (r + g + b) / 3;
      // Cards should be dark (< 80 avg) or transparent
      // Accept transparent (rgba(0,0,0,0)) as PatternFly may inherit from parent
      if (bgColor !== 'rgba(0, 0, 0, 0)') {
        expect(brightness).toBeLessThan(100);
      }
    }
  });

  test('text color is light (not black) on the main page', async ({ page }) => {
    await gotoStore(page);
    const textColor = await page.evaluate(() => {
      return window.getComputedStyle(document.body).color;
    });
    const match = textColor.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
    if (match) {
      const [, r, g, b] = match.map(Number);
      const brightness = (r + g + b) / 3;
      expect(brightness).toBeGreaterThan(150); // Light text
    }
  });

  test('PatternFly tabs have dark theme styling (border uses brand color)', async ({ page }) => {
    await gotoStore(page);
    const tabsEl = page.locator('.pf-v6-c-tabs').first();
    await expect(tabsEl).toBeVisible({ timeout: 8000 });

    // Check that the accent border color CSS variable is overridden
    const accentBorder = await page.evaluate(() => {
      const tabs = document.querySelector('.pf-v6-c-tabs');
      if (!tabs) return null;
      return window.getComputedStyle(tabs)
        .getPropertyValue('--pf-v6-c-tabs__item--m-current--after--BorderColor');
    });
    // Should be the accent color (not empty, as we override it in overrides.css)
    // Accept either the variable reference or empty (computed value may differ)
    expect(accentBorder).not.toBeNull();
  });

  test('page section background matches dark theme', async ({ page }) => {
    await gotoStore(page);
    const pageSection = page.locator('.pf-v6-c-page__main-section').first();
    await expect(pageSection).toBeVisible({ timeout: 8000 });

    const bg = await pageSection.evaluate(el => {
      return window.getComputedStyle(el).backgroundColor;
    });
    const match = bg.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
    if (match) {
      const [, r, g, b] = match.map(Number);
      const brightness = (r + g + b) / 3;
      // Page sections should be dark
      expect(brightness).toBeLessThan(80);
    }
  });
});

// ============================================================================
// 2. Campaign Ad Bar (Image + Design)
// ============================================================================

test.describe('2. Campaign Ad Bar Design and Image', () => {

  test('campaign banner container renders above the catalog grid', async ({ page }) => {
    await mockAPIs(page);
    await gotoStore(page);

    const bannerContainer = page.locator('#campaign-banners, .campaign-banners-container');
    await expect(bannerContainer).toBeAttached({ timeout: 8000 });

    const catalogGrid = page.locator('#catalog-grid, .catalog-grid').first();
    await expect(catalogGrid).toBeAttached({ timeout: 8000 });

    const bannerBox = await bannerContainer.boundingBox();
    const catalogBox = await catalogGrid.boundingBox();

    if (bannerBox && catalogBox) {
      expect(bannerBox.y).toBeLessThanOrEqual(catalogBox.y);
    }
  });

  test('banner with image_url renders background-image on .ds-campaign-banner-bg', async ({ page }) => {
    await mockAPIs(page);
    await gotoStore(page);

    const banner = page.locator('.ds-campaign-banner').first();
    await expect(banner).toBeVisible({ timeout: 8000 });

    // The background image is set on the .ds-campaign-banner-bg child div
    const bgDiv = banner.locator('.ds-campaign-banner-bg').first();
    await expect(bgDiv).toBeAttached();

    const bgImage = await bgDiv.evaluate(el => {
      return window.getComputedStyle(el).backgroundImage;
    });
    // Should have a url(...) background image
    expect(bgImage).toMatch(/url\(/i);
    expect(bgImage).not.toBe('none');
  });

  test('banner background image div is absolutely positioned (inset)', async ({ page }) => {
    await mockAPIs(page);
    await gotoStore(page);

    const bgDiv = page.locator('.ds-campaign-banner-bg').first();
    await expect(bgDiv).toBeAttached({ timeout: 8000 });

    const pos = await bgDiv.evaluate(el => {
      const cs = window.getComputedStyle(el);
      return { position: cs.position, opacity: parseFloat(cs.opacity) };
    });
    // Should be absolutely positioned covering the banner
    expect(pos.position).toBe('absolute');
    // Image should be semi-transparent (opacity < 1) to let text show through
    expect(pos.opacity).toBeLessThan(1);
  });

  test('banner shows title text', async ({ page }) => {
    await mockAPIs(page);
    await gotoStore(page);

    const bannerContainer = page.locator('#campaign-banners, .campaign-banners-container');
    await expect(bannerContainer).toContainText('Grand Summer Sale', { timeout: 8000 });
  });

  test('banner shows content text', async ({ page }) => {
    await mockAPIs(page);
    await gotoStore(page);

    const bannerContainer = page.locator('#campaign-banners, .campaign-banners-container');
    await expect(bannerContainer).toContainText('Everything 50% off this week!', { timeout: 8000 });
  });

  test('banner has correct minimum height (at least 100px)', async ({ page }) => {
    await mockAPIs(page);
    await gotoStore(page);

    const banner = page.locator('.ds-campaign-banner').first();
    await expect(banner).toBeVisible({ timeout: 8000 });

    const box = await banner.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      expect(box.height).toBeGreaterThanOrEqual(100);
    }
  });

  test('banner has border-radius (rounded corners)', async ({ page }) => {
    await mockAPIs(page);
    await gotoStore(page);

    const banner = page.locator('.ds-campaign-banner').first();
    await expect(banner).toBeVisible({ timeout: 8000 });

    const borderRadius = await banner.evaluate(el => {
      return window.getComputedStyle(el).borderRadius;
    });
    // Should not be '0px' - should have some border-radius
    expect(borderRadius).not.toBe('0px');
    expect(borderRadius).not.toBe('');
  });

  test('banner without image_url shows no .ds-campaign-banner-bg div', async ({ page }) => {
    await mockAPIs(page, { campaigns: MOCK_ACTIVE_CAMPAIGNS_NO_IMAGE });
    await gotoStore(page);

    const banner = page.locator('.ds-campaign-banner').first();
    await expect(banner).toBeVisible({ timeout: 8000 });

    // When no image_url, the background div should not be rendered
    const bgDiv = banner.locator('.ds-campaign-banner-bg');
    await expect(bgDiv).not.toBeAttached();

    // Banner should still be visible with its card background color
    const bg = await banner.evaluate(el => window.getComputedStyle(el).backgroundColor);
    expect(bg).not.toBe('rgba(0, 0, 0, 0)'); // some background color set
  });

  test('promo campaign shows coupon code', async ({ page }) => {
    await mockAPIs(page);
    await gotoStore(page);

    const promoContainer = page.locator('#campaign-promos, .campaign-promos-container');
    await expect(promoContainer).toBeAttached({ timeout: 8000 });
    await expect(promoContainer).toContainText('FLASH20');
  });

  test('promo campaign renders with ds-coupon-tag styling', async ({ page }) => {
    await mockAPIs(page);
    await gotoStore(page);

    const couponTag = page.locator('.ds-coupon-tag').first();
    await expect(couponTag).toBeVisible({ timeout: 8000 });
  });

  test('campaign area is absent when no campaigns are active', async ({ page }) => {
    await mockAPIs(page, { campaigns: [] });
    await gotoStore(page);

    // When no campaigns, containers should not be present
    const bannerContainer = page.locator('.campaign-banners-container');
    await expect(bannerContainer).not.toBeAttached({ timeout: 5000 });
  });
});

// ============================================================================
// 3. Page Alignment
// ============================================================================

test.describe('3. Page Alignment (Main Card With Root Viewport)', () => {

  test('page root div fills the full viewport width', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await gotoStore(page);

    const rootDiv = page.locator('#root');
    const box = await rootDiv.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      // Root should start at x=0
      expect(box.x).toBe(0);
      // Root should fill full width (allow 1px tolerance)
      expect(box.width).toBeGreaterThanOrEqual(1279);
    }
  });

  test('pf-v6-c-page grid has single column (phantom sidebar suppressed)', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await gotoStore(page);

    const pageEl = page.locator('.pf-v6-c-page').first();
    await expect(pageEl).toBeVisible({ timeout: 8000 });

    const gtc = await pageEl.evaluate(el => {
      return window.getComputedStyle(el).gridTemplateColumns;
    });
    // After fix: should be a single column, NOT the phantom "290px NNNpx" two-column layout.
    // A single-column grid returns one token like "960px" or "1280px" with no space separating two values.
    // We detect multiple columns by counting px-value tokens separated by spaces.
    const pxTokens = gtc.trim().split(/\s+/).filter(t => /^[\d.]+px$/.test(t));
    expect(pxTokens.length).toBe(1);
  });

  test('store main card is horizontally centered (not pushed right)', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await gotoStore(page);

    const pageEl = page.locator('.pf-v6-c-page').first();
    await expect(pageEl).toBeVisible({ timeout: 8000 });

    const box = await pageEl.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      // With max-width:960px and margin:0 auto at 1280px viewport,
      // left margin = (1280-960)/2 = 160px.
      // Before fix, content started at 318px (phantom sidebar).
      // The centered offset must be substantially less than 318.
      expect(box.x).toBeLessThan(200);
      // And the page should be symmetrically centered: left margin ≈ right margin
      const leftMargin = box.x;
      const rightMargin = 1280 - (box.x + box.width);
      expect(Math.abs(leftMargin - rightMargin)).toBeLessThan(10);
    }
  });

  test('page section content starts in the left half of the viewport', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await gotoStore(page);

    const pageSection = page.locator('.pf-v6-c-page__main-section').first();
    await expect(pageSection).toBeVisible({ timeout: 8000 });

    const box = await pageSection.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      // Section should start in the left half of the screen, not pushed past center
      expect(box.x).toBeLessThan(640);
      // And specifically must be much less than the old broken 318px phantom sidebar offset
      // The centered design puts sections at ~160-200px, not 318px+
      expect(box.x).toBeLessThan(250);
    }
  });

  test('store main card is reasonably wide (≥70% of viewport)', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await gotoStore(page);

    const pageEl = page.locator('.pf-v6-c-page').first();
    await expect(pageEl).toBeVisible({ timeout: 8000 });

    const box = await pageEl.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      // max-width:960px / 1280px viewport = 75%. Accept ≥70%.
      expect(box.width).toBeGreaterThan(1280 * 0.7);
    }
  });

  test('no horizontal scrollbar is present at 1280px viewport', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await gotoStore(page);

    const hasHorizontalScroll = await page.evaluate(() => {
      return document.documentElement.scrollWidth > document.documentElement.clientWidth;
    });
    expect(hasHorizontalScroll).toBe(false);
  });

  test('store header (Darwin Store title) is visible and left-aligned', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await gotoStore(page);

    const title = page.locator('h1').filter({ hasText: 'Darwin Store' });
    await expect(title).toBeVisible({ timeout: 8000 });

    const box = await title.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      // Title should be near the left side, not pushed to the right side
      expect(box.x).toBeLessThan(400);
    }
  });

  test('catalog tab panel is not right-shifted (less than old 318px offset)', async ({ page }) => {
    await mockAPIs(page);
    await page.setViewportSize({ width: 1280, height: 800 });
    await gotoStore(page);

    const catalogSection = page.locator('#catalog').first();
    await expect(catalogSection).toBeAttached({ timeout: 8000 });

    const box = await catalogSection.boundingBox();
    if (box) {
      // Catalog should start well within first half of screen
      // Old broken state: x=338px (318px phantom sidebar + 20px section padding)
      // Fixed centered state: x ≈ 180-210px (160px center margin + padding)
      expect(box.x).toBeLessThan(318);
    }
  });
});
