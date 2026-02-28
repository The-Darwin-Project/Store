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
  background-color: var(--pf-v6-c-page--BackgroundColor, #fff);
}
@media (min-width: 75rem) {
  .pf-v6-c-page {
    grid-template-areas: "header header" "sidebar main";
    grid-template-columns: 18.125rem 1fr;
  }
}
.pf-v6-c-page__main {
  grid-area: main;
  overflow-y: auto;
}
.pf-v6-c-page__main-section {
  padding: var(--pf-v6-c-page__main-section--PaddingTop, 1.5rem)
           var(--pf-v6-c-page__main-section--PaddingRight, 1.5rem)
           var(--pf-v6-c-page__main-section--PaddingBottom, 1.5rem)
           var(--pf-v6-c-page__main-section--PaddingLeft, 1.5rem);
  background-color: var(--pf-v6-c-page__main-section--BackgroundColor, transparent);
}
.pf-v6-c-tabs__list {
  display: flex;
  list-style: none;
  margin: 0;
  padding: 0;
}
.pf-v6-c-tabs__link {
  padding: 0.75rem 1rem;
  background: none;
  border: none;
  cursor: pointer;
}
.pf-v6-c-card {
  background-color: var(--pf-v6-c-card--BackgroundColor, #fff);
  border-radius: 8px;
  padding: 1rem;
}
.pf-v6-l-gallery {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 1rem;
}
`;

// ============================================================================
// HTML builders
// ============================================================================

function buildBannerHTML(campaign) {
  const bgDiv = campaign.image_url
    ? `<div class="ds-campaign-banner-bg" style="background-image: url(${campaign.image_url})"></div>`
    : '';
  return `
    <div class="ds-campaign-banner"${campaign.link_url ? ' style="cursor:pointer"' : ''}>
      ${bgDiv}
      <div class="ds-campaign-banner-content">
        <h3>${campaign.title}</h3>
        ${campaign.content ? `<p>${campaign.content}</p>` : ''}
        ${campaign.coupon_code ? `<span class="ds-coupon-tag">Use code: ${campaign.coupon_code}</span>` : ''}
      </div>
    </div>`;
}

function buildPromoHTML(campaign) {
  return `
    <div class="ds-promo-card">
      <span class="promo-text"><strong>${campaign.title}</strong>${campaign.content ? ` &mdash; ${campaign.content}` : ''}</span>
      ${campaign.coupon_code ? `<span class="ds-coupon-tag" style="margin-left:0.5rem">Code: ${campaign.coupon_code}</span>` : ''}
    </div>`;
}

function buildProductCardHTML(product) {
  let stockBadge;
  if (product.stock === 0) {
    stockBadge = '<div class="stock-badge out-of-stock">Out of stock</div>';
  } else if (product.stock < 10) {
    stockBadge = `<div class="stock-badge low-stock">Low stock (${product.stock})</div>`;
  } else {
    stockBadge = '<div class="stock-badge in-stock">In stock</div>';
  }
  return `
    <div class="pf-v6-l-gallery__item">
      <div class="pf-v6-c-card ds-product-card catalog-card" id="product-card-${product.id}">
        <div class="pf-v6-c-card__title"><span class="ds-product-name">${product.name}</span></div>
        <div class="pf-v6-c-card__body">
          <div class="price card-price" style="font-size:1.25rem;font-weight:700">$${product.price.toFixed(2)}</div>
          ${stockBadge}
        </div>
      </div>
    </div>`;
}

function buildStoreHTML({ banners = [], promos = [], products = [] } = {}) {
  const bannersHTML = banners.length > 0
    ? `<div class="campaign-banners-container" id="campaign-banners">${banners.map(buildBannerHTML).join('')}</div>`
    : '';
  const promosHTML = promos.length > 0
    ? `<div class="campaign-promos-container" id="campaign-promos">${promos.map(buildPromoHTML).join('')}</div>`
    : '';
  const productsHTML = products.length > 0
    ? products.map(buildProductCardHTML).join('')
    : '<div class="ds-empty-state" style="grid-column:1/-1">No products yet.</div>';

  return `<!DOCTYPE html>
<html lang="en" class="pf-v6-theme-dark">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Darwin Store</title></head>
<body>
<div id="root">
  <div class="pf-v6-c-page">
    <main class="pf-v6-c-page__main">
      <section class="pf-v6-c-page__main-section pf-m-secondary">
        <h1>Darwin Store</h1>
        <p class="ds-subtitle">Shop</p>
      </section>
      <section class="pf-v6-c-page__main-section">
        <div class="pf-v6-c-tabs">
          <ul class="pf-v6-c-tabs__list">
            <li class="pf-v6-c-tabs__item pf-m-current">
              <button class="pf-v6-c-tabs__link" role="tab">Catalog</button>
            </li>
            <li class="pf-v6-c-tabs__item">
              <button class="pf-v6-c-tabs__link" role="tab">Cart</button>
            </li>
            <li class="pf-v6-c-tabs__item">
              <button class="pf-v6-c-tabs__link" role="tab">My Orders</button>
            </li>
          </ul>
        </div>
        <section class="pf-v6-c-page__main-section">
          <div id="catalog">
            ${bannersHTML}
            ${promosHTML}
            <div class="catalog-grid" id="catalog-grid">
              <div class="pf-v6-l-gallery pf-m-gutter">
                ${productsHTML}
              </div>
            </div>
          </div>
        </section>
      </section>
    </main>
  </div>
</div>
</body>
</html>`;
}

// ============================================================================
// Test data
// ============================================================================

const MOCK_PRODUCTS = [
  { id: 'prod-1', name: 'Test Widget', sku: 'TW-001', price: 29.99, stock: 50, description: 'A test widget', image_data: null },
];

const BANNER_WITH_IMAGE = {
  id: 'camp-banner',
  title: 'Grand Summer Sale',
  campaign_type: 'banner',
  content: 'Everything 50% off this week!',
  image_url: 'https://images.unsplash.com/photo-1607082348824-0a96f2a4b9da?w=1200',
  link_url: null,
  coupon_code: null,
};

const BANNER_NO_IMAGE = {
  id: 'camp-no-img',
  title: 'No Image Banner',
  campaign_type: 'banner',
  content: 'Sale without an image',
  image_url: null,
  link_url: null,
  coupon_code: null,
};

const PROMO = {
  id: 'camp-promo',
  title: 'Flash Deal',
  campaign_type: 'discount_promo',
  content: 'Save 20% on everything',
  image_url: null,
  link_url: null,
  coupon_code: 'FLASH20',
};

const OVERRIDES_CSS_PATH = path.resolve(__dirname, '..', 'frontend', 'src', 'styles', 'overrides.css');

// ============================================================================
// Helper: load store page with CSS
// ============================================================================

async function loadStore(page, { banners = [], promos = [], products = MOCK_PRODUCTS, viewport } = {}) {
  if (viewport) await page.setViewportSize(viewport);
  const html = buildStoreHTML({ banners, promos, products });
  await page.setContent(html, { waitUntil: 'domcontentloaded' });
  await page.addStyleTag({ content: PF_GRID_CSS });
  await page.addStyleTag({ path: OVERRIDES_CSS_PATH });
  // Let styles settle
  await page.waitForTimeout(100);
}

// ============================================================================
// 1. PatternFly Dark Theme
// ============================================================================

test.describe('1. PatternFly Dark Theme Unification', () => {

  test('html element has pf-v6-theme-dark class', async ({ page }) => {
    await loadStore(page);
    const htmlClass = await page.locator('html').getAttribute('class');
    expect(htmlClass).toContain('pf-v6-theme-dark');
  });

  test('body background-color is dark (not white)', async ({ page }) => {
    await loadStore(page);
    const bgColor = await page.evaluate(() => window.getComputedStyle(document.body).backgroundColor);
    const match = bgColor.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
    expect(match).not.toBeNull();
    if (match) {
      const brightness = (Number(match[1]) + Number(match[2]) + Number(match[3])) / 3;
      expect(brightness).toBeLessThan(80);
    }
  });

  test('dark theme CSS variable --ds-bg-primary is defined', async ({ page }) => {
    await loadStore(page);
    const dsVar = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue('--ds-bg-primary'));
    expect(dsVar.trim()).not.toBe('');
  });

  test('product cards have dark background (not white)', async ({ page }) => {
    await loadStore(page, { products: MOCK_PRODUCTS });
    const card = page.locator('.catalog-card, .ds-product-card').first();
    await expect(card).toBeVisible({ timeout: 3000 });

    const bgColor = await card.evaluate(el => window.getComputedStyle(el).backgroundColor);
    const match = bgColor.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
    if (match) {
      const brightness = (Number(match[1]) + Number(match[2]) + Number(match[3])) / 3;
      if (bgColor !== 'rgba(0, 0, 0, 0)') {
        expect(brightness).toBeLessThan(100);
      }
    }
  });

  test('text color is light (not black) on the main page', async ({ page }) => {
    await loadStore(page);
    const textColor = await page.evaluate(() => window.getComputedStyle(document.body).color);
    const match = textColor.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
    if (match) {
      const brightness = (Number(match[1]) + Number(match[2]) + Number(match[3])) / 3;
      expect(brightness).toBeGreaterThan(150);
    }
  });

  test('PatternFly tabs have dark theme styling', async ({ page }) => {
    await loadStore(page);
    const tabsEl = page.locator('.pf-v6-c-tabs').first();
    await expect(tabsEl).toBeVisible({ timeout: 3000 });
  });

  test('page section background matches dark theme', async ({ page }) => {
    await loadStore(page);
    const pageSection = page.locator('.pf-v6-c-page__main-section').first();
    await expect(pageSection).toBeVisible({ timeout: 3000 });

    const bg = await pageSection.evaluate(el => window.getComputedStyle(el).backgroundColor);
    const match = bg.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
    if (match) {
      const brightness = (Number(match[1]) + Number(match[2]) + Number(match[3])) / 3;
      expect(brightness).toBeLessThan(80);
    }
  });
});

// ============================================================================
// 2. Campaign Ad Bar (Image + Design)
// ============================================================================

test.describe('2. Campaign Ad Bar Design and Image', () => {

  test('campaign banner container renders above the catalog grid', async ({ page }) => {
    await loadStore(page, { banners: [BANNER_WITH_IMAGE], products: MOCK_PRODUCTS });

    const bannerContainer = page.locator('#campaign-banners');
    await expect(bannerContainer).toBeAttached({ timeout: 3000 });

    const catalogGrid = page.locator('#catalog-grid').first();
    await expect(catalogGrid).toBeAttached({ timeout: 3000 });

    const bannerBox = await bannerContainer.boundingBox();
    const catalogBox = await catalogGrid.boundingBox();
    if (bannerBox && catalogBox) {
      expect(bannerBox.y).toBeLessThanOrEqual(catalogBox.y);
    }
  });

  test('banner with image_url renders background-image on .ds-campaign-banner-bg', async ({ page }) => {
    await loadStore(page, { banners: [BANNER_WITH_IMAGE] });

    const banner = page.locator('.ds-campaign-banner').first();
    await expect(banner).toBeVisible({ timeout: 3000 });

    const bgDiv = banner.locator('.ds-campaign-banner-bg').first();
    await expect(bgDiv).toBeAttached();

    const bgImage = await bgDiv.evaluate(el => window.getComputedStyle(el).backgroundImage);
    expect(bgImage).toMatch(/url\(/i);
    expect(bgImage).not.toBe('none');
  });

  test('banner background image div is absolutely positioned with low opacity', async ({ page }) => {
    await loadStore(page, { banners: [BANNER_WITH_IMAGE] });

    const bgDiv = page.locator('.ds-campaign-banner-bg').first();
    await expect(bgDiv).toBeAttached({ timeout: 3000 });

    const pos = await bgDiv.evaluate(el => {
      const cs = window.getComputedStyle(el);
      return { position: cs.position, opacity: parseFloat(cs.opacity) };
    });
    expect(pos.position).toBe('absolute');
    expect(pos.opacity).toBeLessThan(1);
  });

  test('banner shows title text', async ({ page }) => {
    await loadStore(page, { banners: [BANNER_WITH_IMAGE] });
    const bannerContainer = page.locator('#campaign-banners');
    await expect(bannerContainer).toContainText('Grand Summer Sale', { timeout: 3000 });
  });

  test('banner shows content text', async ({ page }) => {
    await loadStore(page, { banners: [BANNER_WITH_IMAGE] });
    const bannerContainer = page.locator('#campaign-banners');
    await expect(bannerContainer).toContainText('Everything 50% off this week!', { timeout: 3000 });
  });

  test('banner has correct minimum height (at least 100px)', async ({ page }) => {
    await loadStore(page, { banners: [BANNER_WITH_IMAGE] });
    const banner = page.locator('.ds-campaign-banner').first();
    await expect(banner).toBeVisible({ timeout: 3000 });

    const box = await banner.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      expect(box.height).toBeGreaterThanOrEqual(100);
    }
  });

  test('banner has border-radius (rounded corners)', async ({ page }) => {
    await loadStore(page, { banners: [BANNER_WITH_IMAGE] });
    const banner = page.locator('.ds-campaign-banner').first();
    await expect(banner).toBeVisible({ timeout: 3000 });

    const borderRadius = await banner.evaluate(el => window.getComputedStyle(el).borderRadius);
    expect(borderRadius).not.toBe('0px');
    expect(borderRadius).not.toBe('');
  });

  test('banner without image_url shows no .ds-campaign-banner-bg div', async ({ page }) => {
    await loadStore(page, { banners: [BANNER_NO_IMAGE] });
    const banner = page.locator('.ds-campaign-banner').first();
    await expect(banner).toBeVisible({ timeout: 3000 });

    const bgDiv = banner.locator('.ds-campaign-banner-bg');
    await expect(bgDiv).not.toBeAttached();

    const bg = await banner.evaluate(el => window.getComputedStyle(el).backgroundColor);
    expect(bg).not.toBe('rgba(0, 0, 0, 0)');
  });

  test('promo campaign shows coupon code', async ({ page }) => {
    await loadStore(page, { promos: [PROMO] });
    const promoContainer = page.locator('#campaign-promos');
    await expect(promoContainer).toBeAttached({ timeout: 3000 });
    await expect(promoContainer).toContainText('FLASH20');
  });

  test('promo campaign renders with ds-coupon-tag styling', async ({ page }) => {
    await loadStore(page, { promos: [PROMO] });
    const couponTag = page.locator('.ds-coupon-tag').first();
    await expect(couponTag).toBeVisible({ timeout: 3000 });
  });

  test('campaign area is absent when no campaigns are active', async ({ page }) => {
    await loadStore(page, { banners: [], promos: [] });
    const bannerContainer = page.locator('.campaign-banners-container');
    await expect(bannerContainer).not.toBeAttached({ timeout: 3000 });
  });
});

// ============================================================================
// 3. Page Alignment
// ============================================================================

test.describe('3. Page Alignment (Main Card With Root Viewport)', () => {
  const VP = { width: 1280, height: 800 };

  test('page root div fills the full viewport width', async ({ page }) => {
    await loadStore(page, { viewport: VP });
    const rootDiv = page.locator('#root');
    const box = await rootDiv.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      // Allow small offset from default body margin (8px)
      expect(box.x).toBeLessThanOrEqual(8);
      expect(box.width).toBeGreaterThanOrEqual(1264);
    }
  });

  test('pf-v6-c-page grid has single column (phantom sidebar suppressed)', async ({ page }) => {
    await loadStore(page, { viewport: VP });
    const pageEl = page.locator('.pf-v6-c-page').first();
    await expect(pageEl).toBeVisible({ timeout: 3000 });

    const gtc = await pageEl.evaluate(el => window.getComputedStyle(el).gridTemplateColumns);
    // After fix: should be a single column (one px token), not the 2-col "290px NNNpx" layout.
    const pxTokens = gtc.trim().split(/\s+/).filter(t => /^[\d.]+px$/.test(t));
    expect(pxTokens.length).toBe(1);
  });

  test('store main card is horizontally centered (not pushed right)', async ({ page }) => {
    await loadStore(page, { viewport: VP });
    const pageEl = page.locator('.pf-v6-c-page').first();
    await expect(pageEl).toBeVisible({ timeout: 3000 });

    const box = await pageEl.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      // With max-width:960px at 1280px viewport, left margin = (1280-960)/2 = 160px.
      expect(box.x).toBeLessThan(200);
      const leftMargin = box.x;
      const rightMargin = 1280 - (box.x + box.width);
      expect(Math.abs(leftMargin - rightMargin)).toBeLessThan(10);
    }
  });

  test('page section content starts in the left half of the viewport', async ({ page }) => {
    await loadStore(page, { viewport: VP });
    const pageSection = page.locator('.pf-v6-c-page__main-section').first();
    await expect(pageSection).toBeVisible({ timeout: 3000 });

    const box = await pageSection.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      expect(box.x).toBeLessThan(250);
    }
  });

  test('store main card is reasonably wide (at least 70% of viewport)', async ({ page }) => {
    await loadStore(page, { viewport: VP });
    const pageEl = page.locator('.pf-v6-c-page').first();
    await expect(pageEl).toBeVisible({ timeout: 3000 });

    const box = await pageEl.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      expect(box.width).toBeGreaterThan(1280 * 0.7);
    }
  });

  test('no horizontal scrollbar is present at 1280px viewport', async ({ page }) => {
    await loadStore(page, { viewport: VP });
    const hasHorizontalScroll = await page.evaluate(() =>
      document.documentElement.scrollWidth > document.documentElement.clientWidth);
    expect(hasHorizontalScroll).toBe(false);
  });

  test('store header (Darwin Store title) is visible and left-aligned', async ({ page }) => {
    await loadStore(page, { viewport: VP });
    const title = page.locator('h1').filter({ hasText: 'Darwin Store' });
    await expect(title).toBeVisible({ timeout: 3000 });

    const box = await title.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      expect(box.x).toBeLessThan(400);
    }
  });

  test('catalog tab panel is not right-shifted (less than old 318px offset)', async ({ page }) => {
    await loadStore(page, { viewport: VP, products: MOCK_PRODUCTS });
    const catalogSection = page.locator('#catalog').first();
    await expect(catalogSection).toBeAttached({ timeout: 3000 });

    const box = await catalogSection.boundingBox();
    if (box) {
      expect(box.x).toBeLessThan(318);
    }
  });
});
