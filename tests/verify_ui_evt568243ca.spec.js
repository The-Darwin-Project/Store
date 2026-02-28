// tests/verify_ui_evt568243ca.spec.js
// @ai-rules:
// 1. [Constraint]: Self-contained -- no server needed. Uses page.setContent() + addStyleTag().
// 2. [Pattern]: Includes minimal PF6 grid CSS to test our override beats the media query.
// 3. [Gotcha]: PF6 media query at 75rem (1200px) forces 2-col grid; overrides.css must beat it.

const { test, expect } = require('@playwright/test');
const path = require('path');

// ============================================================================
// Minimal PatternFly 6 CSS subset for layout testing.
// Includes the grid rules our overrides must beat.
// ============================================================================
const PF_GRID_CSS = `
.pf-v6-c-page {
  display: grid;
  grid-template-areas: "header" "main";
  grid-template-rows: max-content 1fr;
  grid-template-columns: 1fr;
  height: 100vh;
}
@media (min-width: 75rem) {
  .pf-v6-c-page {
    grid-template-areas: "header header" "sidebar main";
    grid-template-columns: 18.125rem 1fr;
  }
}
.pf-v6-c-page__main-section {
  grid-area: main;
  padding: 1.5rem;
}
.pf-v6-c-tabs { display: flex; border-bottom: 1px solid #444; }
.pf-v6-c-tabs__link { padding: 0.5rem 1rem; color: inherit; text-decoration: none; }
`;

// ============================================================================
// Path to overrides.css (loaded via addStyleTag)
// ============================================================================
const OVERRIDES_CSS_PATH = path.resolve(__dirname, '../frontend/src/styles/overrides.css');

// ============================================================================
// Build static HTML matching React component output
// ============================================================================
function buildStoreHTML({ campaigns = [], products = [] } = {}) {
  const banners = campaigns.filter(c => c.type === 'banner');
  const promos = campaigns.filter(c => c.type !== 'banner');

  const bannerHTML = banners.length > 0 ? `
    <div class="campaign-banners-container" id="campaign-banners">
      ${banners.map(b => `
        <div class="ds-campaign-banner">
          ${b.image_url ? `<div class="ds-campaign-banner-bg" style="background-image: url(${b.image_url})"></div>` : ''}
          <div class="ds-campaign-banner-content">
            <h3>${b.title}</h3>
            ${b.content ? `<p>${b.content}</p>` : ''}
            ${b.coupon_code ? `<span class="ds-coupon-tag">Use code: ${b.coupon_code}</span>` : ''}
          </div>
        </div>
      `).join('')}
    </div>` : '';

  const promoHTML = promos.length > 0 ? `
    <div class="campaign-promos-container" id="campaign-promos">
      ${promos.map(p => `
        <div class="ds-promo-card">
          <span class="promo-text"><strong>${p.title}</strong>${p.content ? ` &mdash; ${p.content}` : ''}</span>
          ${p.coupon_code ? `<span class="ds-coupon-tag" style="margin-left:0.5rem">Code: ${p.coupon_code}</span>` : ''}
        </div>
      `).join('')}
    </div>` : '';

  const productHTML = products.map(p => `
    <div class="ds-product-card catalog-card pf-v6-c-card" id="product-card-${p.id}">
      <div class="pf-v6-c-card__title"><span class="ds-product-name">${p.name}</span></div>
      <div class="pf-v6-c-card__body">
        <div class="price card-price" style="font-size:1.25rem;font-weight:700">$${(Number(p.price)||0).toFixed(2)}</div>
        ${p.stock === 0
          ? '<div class="stock-badge out-of-stock">Out of stock</div>'
          : p.stock < 10
            ? `<div class="stock-badge low-stock">Low stock (${p.stock})</div>`
            : '<div class="stock-badge in-stock">In stock</div>'}
      </div>
    </div>
  `).join('');

  return `<!DOCTYPE html>
<html class="pf-v6-theme-dark">
<head><meta charset="utf-8"><title>Darwin Store</title></head>
<body style="margin:0">
<div id="root">
  <div class="pf-v6-c-page">
    <header class="pf-v6-c-page__header" style="grid-area:header;padding:1rem">
      <h1>Darwin Store</h1>
    </header>
    <main class="pf-v6-c-page__main-section">
      <div class="pf-v6-c-tabs">
        <a class="pf-v6-c-tabs__link pf-m-current">Catalog</a>
        <a class="pf-v6-c-tabs__link">Orders</a>
      </div>
      <div id="catalog">
        ${bannerHTML}
        ${promoHTML}
        <div class="catalog-grid" id="catalog-grid">
          ${productHTML || '<div class="ds-empty-state">No products yet.</div>'}
        </div>
      </div>
    </main>
  </div>
</div>
</body>
</html>`;
}

// ============================================================================
// Helpers
// ============================================================================

const MOCK_PRODUCTS = [
  { id: 'prod-1', name: 'Test Widget', sku: 'TW-001', price: 29.99, stock: 50, description: 'A test widget', image_data: null },
];

const MOCK_CAMPAIGNS_WITH_IMAGE = [
  {
    id: 'camp-banner', title: 'Grand Summer Sale', type: 'banner',
    content: 'Everything 50% off this week!',
    image_url: 'https://images.unsplash.com/photo-1607082348824-0a96f2a4b9da?w=1200',
    coupon_code: null, link_url: null,
  },
  {
    id: 'camp-promo', title: 'Flash Deal', type: 'discount_promo',
    content: 'Save 20% on everything',
    image_url: null, coupon_code: 'FLASH20', link_url: null,
  },
];

const MOCK_CAMPAIGNS_NO_IMAGE = [
  {
    id: 'camp-no-img', title: 'No Image Banner', type: 'banner',
    content: 'Sale without an image',
    image_url: null, coupon_code: null, link_url: null,
  },
];

async function loadStore(page, { campaigns, products, width = 1280, height = 800 } = {}) {
  await page.setViewportSize({ width, height });
  const html = buildStoreHTML({
    campaigns: campaigns !== undefined ? campaigns : MOCK_CAMPAIGNS_WITH_IMAGE,
    products: products !== undefined ? products : MOCK_PRODUCTS,
  });
  await page.setContent(html);
  await page.addStyleTag({ path: OVERRIDES_CSS_PATH });
  await page.addStyleTag({ content: PF_GRID_CSS });
}

// ============================================================================
// 1. PatternFly Dark Theme
// ============================================================================

test.describe('1. PatternFly Dark Theme Unification', () => {

  test('html element has pf-v6-theme-dark class', async ({ page }) => {
    await loadStore(page);
    const cls = await page.locator('html').getAttribute('class');
    expect(cls).toContain('pf-v6-theme-dark');
  });

  test('body background-color is dark (not white)', async ({ page }) => {
    await loadStore(page);
    const bg = await page.evaluate(() => window.getComputedStyle(document.body).backgroundColor);
    const m = bg.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
    expect(m).not.toBeNull();
    const brightness = (Number(m[1]) + Number(m[2]) + Number(m[3])) / 3;
    expect(brightness).toBeLessThan(80);
  });

  test('dark theme CSS variable --ds-bg-primary is defined', async ({ page }) => {
    await loadStore(page);
    const v = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue('--ds-bg-primary'));
    expect(v.trim()).not.toBe('');
  });

  test('product card has dark background', async ({ page }) => {
    await loadStore(page);
    const card = page.locator('.catalog-card').first();
    await expect(card).toBeVisible();
    const bg = await card.evaluate(el => window.getComputedStyle(el).backgroundColor);
    const m = bg.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
    if (m) {
      const brightness = (Number(m[1]) + Number(m[2]) + Number(m[3])) / 3;
      expect(brightness).toBeLessThan(100);
    }
  });

  test('text color is light (not black)', async ({ page }) => {
    await loadStore(page);
    const c = await page.evaluate(() => window.getComputedStyle(document.body).color);
    const m = c.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
    if (m) {
      const brightness = (Number(m[1]) + Number(m[2]) + Number(m[3])) / 3;
      expect(brightness).toBeGreaterThan(150);
    }
  });

  test('page section background is dark', async ({ page }) => {
    await loadStore(page);
    const sec = page.locator('.pf-v6-c-page__main-section').first();
    await expect(sec).toBeVisible();
    const bg = await sec.evaluate(el => window.getComputedStyle(el).backgroundColor);
    const m = bg.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
    if (m) {
      const brightness = (Number(m[1]) + Number(m[2]) + Number(m[3])) / 3;
      expect(brightness).toBeLessThan(80);
    }
  });

  test('stock badge uses correct theme colors', async ({ page }) => {
    await loadStore(page);
    const badge = page.locator('.stock-badge.in-stock').first();
    await expect(badge).toBeVisible();
    const bg = await badge.evaluate(el => window.getComputedStyle(el).backgroundColor);
    expect(bg).not.toBe('rgba(0, 0, 0, 0)');
  });
});

// ============================================================================
// 2. Campaign Ad Bar (Image + Design)
// ============================================================================

test.describe('2. Campaign Ad Bar Design and Image', () => {

  test('banner container renders above the catalog grid', async ({ page }) => {
    await loadStore(page);
    const bannerBox = await page.locator('#campaign-banners').boundingBox();
    const gridBox = await page.locator('#catalog-grid').boundingBox();
    expect(bannerBox).not.toBeNull();
    expect(gridBox).not.toBeNull();
    expect(bannerBox.y).toBeLessThanOrEqual(gridBox.y);
  });

  test('banner with image_url renders background-image on .ds-campaign-banner-bg', async ({ page }) => {
    await loadStore(page);
    const bgDiv = page.locator('.ds-campaign-banner-bg').first();
    await expect(bgDiv).toBeAttached();
    const bgImage = await bgDiv.evaluate(el => window.getComputedStyle(el).backgroundImage);
    expect(bgImage).toMatch(/url\(/i);
    expect(bgImage).not.toBe('none');
  });

  test('banner background image div is absolutely positioned with low opacity', async ({ page }) => {
    await loadStore(page);
    const bgDiv = page.locator('.ds-campaign-banner-bg').first();
    await expect(bgDiv).toBeAttached();
    const pos = await bgDiv.evaluate(el => {
      const cs = window.getComputedStyle(el);
      return { position: cs.position, opacity: parseFloat(cs.opacity) };
    });
    expect(pos.position).toBe('absolute');
    expect(pos.opacity).toBeLessThan(1);
  });

  test('banner shows title text', async ({ page }) => {
    await loadStore(page);
    await expect(page.locator('#campaign-banners')).toContainText('Grand Summer Sale');
  });

  test('banner shows content text', async ({ page }) => {
    await loadStore(page);
    await expect(page.locator('#campaign-banners')).toContainText('Everything 50% off this week!');
  });

  test('banner has correct minimum height (at least 100px)', async ({ page }) => {
    await loadStore(page);
    const banner = page.locator('.ds-campaign-banner').first();
    await expect(banner).toBeVisible();
    const box = await banner.boundingBox();
    expect(box).not.toBeNull();
    expect(box.height).toBeGreaterThanOrEqual(100);
  });

  test('banner has border-radius (rounded corners)', async ({ page }) => {
    await loadStore(page);
    const banner = page.locator('.ds-campaign-banner').first();
    await expect(banner).toBeVisible();
    const br = await banner.evaluate(el => window.getComputedStyle(el).borderRadius);
    expect(br).not.toBe('0px');
    expect(br).not.toBe('');
  });

  test('banner without image_url shows no .ds-campaign-banner-bg div', async ({ page }) => {
    await loadStore(page, { campaigns: MOCK_CAMPAIGNS_NO_IMAGE });
    const banner = page.locator('.ds-campaign-banner').first();
    await expect(banner).toBeVisible();
    await expect(banner.locator('.ds-campaign-banner-bg')).not.toBeAttached();
  });

  test('promo campaign shows coupon code', async ({ page }) => {
    await loadStore(page);
    const promo = page.locator('#campaign-promos');
    await expect(promo).toBeAttached();
    await expect(promo).toContainText('FLASH20');
  });

  test('promo campaign renders with ds-coupon-tag styling', async ({ page }) => {
    await loadStore(page);
    const tag = page.locator('.ds-coupon-tag').first();
    await expect(tag).toBeVisible();
  });

  test('campaign area is absent when no campaigns are active', async ({ page }) => {
    await loadStore(page, { campaigns: [] });
    await expect(page.locator('.campaign-banners-container')).not.toBeAttached();
  });
});

// ============================================================================
// 3. Page Alignment
// ============================================================================

test.describe('3. Page Alignment (Main Card With Root Viewport)', () => {

  test('page root div fills the full viewport width', async ({ page }) => {
    await loadStore(page);
    const box = await page.locator('#root').boundingBox();
    expect(box).not.toBeNull();
    expect(box.x).toBeLessThanOrEqual(8); // browser default margin
    expect(box.width).toBeGreaterThanOrEqual(960);
  });

  test('pf-v6-c-page grid has single column (phantom sidebar suppressed)', async ({ page }) => {
    await loadStore(page);
    const gtc = await page.locator('.pf-v6-c-page').first().evaluate(el =>
      window.getComputedStyle(el).gridTemplateColumns);
    // Should be a single column, not "290px NNNpx"
    const pxTokens = gtc.trim().split(/\s+/).filter(t => /^[\d.]+px$/.test(t));
    expect(pxTokens.length).toBe(1);
  });

  test('store main card is horizontally centered (not pushed right)', async ({ page }) => {
    await loadStore(page);
    const pageEl = page.locator('.pf-v6-c-page').first();
    const box = await pageEl.boundingBox();
    expect(box).not.toBeNull();
    // With max-width:960px centered in 1280px viewport: margin ~160px each side
    expect(box.x).toBeLessThan(200);
    const leftMargin = box.x;
    const rightMargin = 1280 - (box.x + box.width);
    expect(Math.abs(leftMargin - rightMargin)).toBeLessThan(10);
  });

  test('page section content starts in the left half of the viewport', async ({ page }) => {
    await loadStore(page);
    const sec = page.locator('.pf-v6-c-page__main-section').first();
    await expect(sec).toBeVisible();
    const box = await sec.boundingBox();
    expect(box).not.toBeNull();
    expect(box.x).toBeLessThan(250);
  });

  test('store main card is reasonably wide (at least 70% of viewport)', async ({ page }) => {
    await loadStore(page);
    const box = await page.locator('.pf-v6-c-page').first().boundingBox();
    expect(box).not.toBeNull();
    expect(box.width).toBeGreaterThan(1280 * 0.7);
  });

  test('no horizontal scrollbar is present at 1280px viewport', async ({ page }) => {
    await loadStore(page);
    const hasScroll = await page.evaluate(() =>
      document.documentElement.scrollWidth > document.documentElement.clientWidth);
    expect(hasScroll).toBe(false);
  });

  test('store header (Darwin Store title) is visible and left-aligned', async ({ page }) => {
    await loadStore(page);
    const title = page.locator('h1').filter({ hasText: 'Darwin Store' });
    await expect(title).toBeVisible();
    const box = await title.boundingBox();
    expect(box).not.toBeNull();
    expect(box.x).toBeLessThan(400);
  });

  test('catalog tab panel is not right-shifted (less than old 318px offset)', async ({ page }) => {
    await loadStore(page);
    const box = await page.locator('#catalog').first().boundingBox();
    if (box) {
      expect(box.x).toBeLessThan(318);
    }
  });
});
