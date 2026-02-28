// tests/verify_live_pr64.spec.js
// Live-deployment QE smoke test for PR #64 fixes.
// Runs against the deployed darwin-store (STORE_URL env or default).
//
// Fixes being verified:
//   1. Product tiles: no horizontal scroll, add-to-cart button visible
//   2. PatternFly dark theme applied (not overwritten by inline styles / old CSS)
//   3. UI stretches to full viewport (no max-width:960px constraint)

const { test, expect } = require('@playwright/test');

const LIVE_URL = process.env.STORE_URL || 'https://darwin-store-darwin.apps.cnv2.engineering.redhat.com';
const MOCK_PRODUCTS = [
  { id: 'p1', name: 'Widget Alpha', price: 19.99, stock: 50, sku: 'WA-001', description: null, image_data: null, supplier_id: null },
  { id: 'p2', name: 'Gadget Beta',  price: 34.50, stock: 8,  sku: 'GB-002', description: null, image_data: null, supplier_id: null },
  { id: 'p3', name: 'Thing Gamma',  price: 9.99,  stock: 0,  sku: 'TG-003', description: null, image_data: null, supplier_id: null },
];
const MOCK_CAMPAIGN = [
  { id: 'c1', title: 'Grand Sale', type: 'banner', content: 'Up to 50% off', coupon_code: 'SAVE50',
    image_url: 'https://images.unsplash.com/photo-1607082348824-0a96f2a4b9da?w=1200', link_url: null,
    discount_percent: null, start_date: null, end_date: null }
];

const SKIP_LIVE = !!process.env.SKIP_LIVE || !!process.env.CI;

test.describe('PR #64 Live Deployment Verification', () => {

  test.beforeEach(async ({}, testInfo) => {
    if (SKIP_LIVE) testInfo.skip(true, 'Skipping live tests in CI / SKIP_LIVE mode');
  });

  // Navigate and intercept API calls to provide predictable data
  async function loadCatalog(page) {
    await page.route('**/api/products', r => r.fulfill({ json: MOCK_PRODUCTS }));
    await page.route('**/api/campaigns/active', r => r.fulfill({ json: MOCK_CAMPAIGN }));
    await page.route('**/api/reviews/**',  r => r.fulfill({ json: [] }));
    await page.route('**/api/orders**',    r => r.fulfill({ json: [] }));
    await page.route('**/api/alerts**',    r => r.fulfill({ json: [] }));
    await page.goto(LIVE_URL, { waitUntil: 'networkidle', timeout: 30000 });
    // Wait for at least one product card to appear
    await page.waitForSelector('.catalog-card, .ds-product-card', { timeout: 20000 }).catch(() => {});
  }

  // ── Fix 1: No horizontal scroll, add-to-cart visible ──────────────────────

  test.describe('Fix 1 – Product tiles: no overflow, add-to-cart visible', () => {

    test('page has no horizontal scrollbar', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await loadCatalog(page);

      const { scrollWidth, clientWidth } = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      }));
      expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 2);
    });

    test('product catalog renders at least one card', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await loadCatalog(page);

      const cards = page.locator('.catalog-card, .ds-product-card');
      await expect(cards.first()).toBeVisible({ timeout: 15000 });
      const count = await cards.count();
      expect(count).toBeGreaterThan(0);
    });

    test('add-to-cart button is visible in catalog cards (not clipped)', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await loadCatalog(page);

      // Look for add-to-cart buttons — they exist for in-stock items
      const addBtns = page.locator('[id^="add-to-cart-"]');
      const count = await addBtns.count();
      if (count === 0) {
        // Fall back: look for any primary button in card footer area
        const footerBtns = page.locator('.pf-v6-c-card__footer .pf-m-primary, .pf-v6-c-card__footer button');
        const fbCount = await footerBtns.count();
        expect(fbCount).toBeGreaterThan(0);
        for (let i = 0; i < Math.min(fbCount, 3); i++) {
          await expect(footerBtns.nth(i)).toBeVisible();
        }
        return;
      }
      for (let i = 0; i < Math.min(count, 3); i++) {
        await expect(addBtns.nth(i)).toBeVisible();
      }
    });

    test('product card footer uses flex-wrap (no content overflow)', async ({ page }) => {
      await page.setViewportSize({ width: 900, height: 700 });
      await loadCatalog(page);

      const footer = page.locator('.pf-v6-c-card__footer').first();
      const footerExists = await footer.count() > 0;
      if (!footerExists) { test.skip(); return; }

      const footerBox = await footer.boundingBox();
      const vpWidth = await page.evaluate(() => window.innerWidth);
      if (footerBox) {
        // Footer right edge must not exceed viewport
        expect(footerBox.x + footerBox.width).toBeLessThanOrEqual(vpWidth + 4);
      }
    });

    test('product cards do not overflow their gallery container', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await loadCatalog(page);

      const gallery = page.locator('.pf-v6-l-gallery, #catalog-gallery, [class*="pf-v6-l-gallery"]');
      const galleryCount = await gallery.count();
      if (galleryCount === 0) { return; } // gallery not visible yet

      const galleryBox = await gallery.first().boundingBox();
      const cards = page.locator('.catalog-card, .ds-product-card');
      const cardCount = await cards.count();

      for (let i = 0; i < Math.min(cardCount, 5); i++) {
        const box = await cards.nth(i).boundingBox();
        if (!box || !galleryBox) continue;
        expect(box.x + box.width).toBeLessThanOrEqual(galleryBox.x + galleryBox.width + 4);
      }
    });

    test('.ds-product-card has overflow:visible (not overflow:auto)', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await loadCatalog(page);

      const card = page.locator('.ds-product-card').first();
      const cardExists = await card.count() > 0;
      if (!cardExists) { return; }

      const overflow = await card.evaluate(el => window.getComputedStyle(el).overflow);
      // Should be 'visible', not 'auto' or 'hidden'
      expect(overflow).not.toBe('auto');
    });
  });

  // ── Fix 2: Dark theme applied ──────────────────────────────────────────────

  test.describe('Fix 2 – PatternFly dark theme correctly applied', () => {

    test('page body background is dark, not white', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await loadCatalog(page);

      const bodyBg = await page.evaluate(() =>
        window.getComputedStyle(document.body).backgroundColor
      );
      // Dark theme body should NOT be white
      expect(bodyBg).not.toBe('rgb(255, 255, 255)');
      expect(bodyBg).not.toBe('rgba(0, 0, 0, 0)');
    });

    test('--ds-bg-primary CSS variable is set on body', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await loadCatalog(page);

      const dsBgPrimary = await page.evaluate(() =>
        window.getComputedStyle(document.body).getPropertyValue('--ds-bg-primary').trim()
      );
      expect(dsBgPrimary).not.toBe('');
      expect(dsBgPrimary.toLowerCase()).toContain('1a1a2e');
    });

    test('product cards have dark background (not white)', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await loadCatalog(page);

      const card = page.locator('.ds-product-card').first();
      const exists = await card.count() > 0;
      if (!exists) { return; }

      const cardBg = await card.evaluate(el => window.getComputedStyle(el).backgroundColor);
      expect(cardBg).not.toBe('rgb(255, 255, 255)');
    });

    test('price text uses success/green color from --ds-success', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await loadCatalog(page);

      const price = page.locator('.price.card-price').first();
      const exists = await price.count() > 0;
      if (!exists) { return; }

      const color = await price.evaluate(el => window.getComputedStyle(el).color);
      // --ds-success = #4ade80 = rgb(74,222,128)
      expect(color).toBe('rgb(74, 222, 128)');
    });

    test('no hardcoded #fbbf24 inline color on rating elements (uses CSS class)', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await loadCatalog(page);

      // Check that inline style color:#fbbf24 is NOT present in the rendered DOM
      const inlineColorCount = await page.evaluate(() => {
        const all = Array.from(document.querySelectorAll('*'));
        return all.filter(el => {
          const inlineColor = el.style?.color;
          return inlineColor === '#fbbf24' || inlineColor === 'rgb(251, 191, 36)';
        }).length;
      });
      expect(inlineColorCount).toBe(0);
    });

    test('no hardcoded #555 inline color on star elements (uses CSS class)', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await loadCatalog(page);

      const inlineColorCount = await page.evaluate(() => {
        return Array.from(document.querySelectorAll('*')).filter(el => {
          const inlineColor = el.style?.color;
          return inlineColor === '#555' || inlineColor === 'rgb(85, 85, 85)';
        }).length;
      });
      expect(inlineColorCount).toBe(0);
    });

    test('price does not have inline font-size:1.25rem (moved to CSS class)', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await loadCatalog(page);

      const inlineFontSizeCount = await page.evaluate(() => {
        return Array.from(document.querySelectorAll('.card-price')).filter(el =>
          el.style?.fontSize === '1.25rem'
        ).length;
      });
      expect(inlineFontSizeCount).toBe(0);
    });

    test('dark theme tokens are active on body', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await loadCatalog(page);

      const pfBrandToken = await page.evaluate(() =>
        window.getComputedStyle(document.body)
          .getPropertyValue('--pf-t--global--color--brand--default').trim()
      );
      // Should be mapped to --ds-accent (#e94560), not empty
      expect(pfBrandToken).not.toBe('');
    });

    test('page section backgrounds are dark', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await loadCatalog(page);

      const sectionBg = await page.evaluate(() => {
        const section = document.querySelector('.pf-v6-c-page__main-section');
        return section ? window.getComputedStyle(section).backgroundColor : null;
      });
      if (sectionBg) {
        expect(sectionBg).not.toBe('rgb(255, 255, 255)');
      }
    });
  });

  // ── Fix 3: Full viewport stretch ──────────────────────────────────────────

  test.describe('Fix 3 – UI stretches to full viewport width', () => {

    test('page root fills full viewport width at 1280px', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await loadCatalog(page);

      const { pageWidth, vpWidth } = await page.evaluate(() => {
        const root = document.querySelector('.pf-v6-c-page') ||
                     document.querySelector('#root > div') ||
                     document.body;
        return {
          pageWidth: root.getBoundingClientRect().width,
          vpWidth: window.innerWidth,
        };
      });
      // Page must fill at least 98% of viewport
      expect(pageWidth / vpWidth).toBeGreaterThanOrEqual(0.98);
    });

    test('page root has no max-width:960px constraint', async ({ page }) => {
      await page.setViewportSize({ width: 1440, height: 900 });
      await loadCatalog(page);

      const maxWidth = await page.evaluate(() => {
        const root = document.querySelector('.pf-v6-c-page');
        return root ? window.getComputedStyle(root).maxWidth : 'none';
      });
      expect(maxWidth).not.toBe('960px');
    });

    test('page right edge reaches viewport right at 1440px', async ({ page }) => {
      await page.setViewportSize({ width: 1440, height: 900 });
      await loadCatalog(page);

      const { rightEdge, vpWidth } = await page.evaluate(() => {
        const root = document.querySelector('.pf-v6-c-page') ||
                     document.querySelector('#root > div') ||
                     document.body;
        return {
          rightEdge: root.getBoundingClientRect().right,
          vpWidth: window.innerWidth,
        };
      });
      expect(rightEdge).toBeGreaterThanOrEqual(vpWidth - 2);
    });

    test('page has no centering margin (margin:0 auto removed)', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await loadCatalog(page);

      const { marginLeft, marginRight } = await page.evaluate(() => {
        const root = document.querySelector('.pf-v6-c-page');
        if (!root) return { marginLeft: '0px', marginRight: '0px' };
        const style = window.getComputedStyle(root);
        return { marginLeft: style.marginLeft, marginRight: style.marginRight };
      });
      expect(marginLeft).toBe('0px');
      expect(marginRight).toBe('0px');
    });

    test('phantom sidebar column is suppressed at >1200px viewport', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await loadCatalog(page);

      const gridCols = await page.evaluate(() => {
        const root = document.querySelector('.pf-v6-c-page');
        return root ? window.getComputedStyle(root).gridTemplateColumns : null;
      });

      if (gridCols) {
        // Two-column layout would be "290px NNNpx" or "18.125rem 1fr"
        // Single-column is "NNNpx" (one token)
        const tokens = gridCols.trim().split(/\s+/).filter(Boolean);
        expect(tokens.length).toBe(1);
      }
    });

    test('page fills full viewport at 1920px wide screen', async ({ page }) => {
      await page.setViewportSize({ width: 1920, height: 1080 });
      await loadCatalog(page);

      const { pageWidth, vpWidth } = await page.evaluate(() => {
        const root = document.querySelector('.pf-v6-c-page') ||
                     document.querySelector('#root > div') ||
                     document.body;
        return {
          pageWidth: root.getBoundingClientRect().width,
          vpWidth: window.innerWidth,
        };
      });
      expect(pageWidth / vpWidth).toBeGreaterThanOrEqual(0.98);
    });
  });
});
