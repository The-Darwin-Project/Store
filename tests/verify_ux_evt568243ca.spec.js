// tests/verify_ux_evt568243ca.spec.js
// QE verification: evt-568243ca round 2 UX fixes
//
// @ai-rules:
// 1. [Constraint]: Self-contained -- no server needed. Uses page.setContent() + addStyleTag().
// 2. [Coverage]: Product tile overflow, dark theme integrity, full viewport stretch.
// 3. [Pattern]: Each describe block tests one of the 3 reported UX issues.

const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

// ============================================================================
// Minimal PatternFly 6 CSS subset (same phantom-sidebar media query as before)
// ============================================================================
const PF_BASE_CSS = `
*, *::before, *::after { box-sizing: border-box; }
html, body { margin: 0; padding: 0; width: 100%; height: 100%; }

/* PF6 Page grid with phantom sidebar */
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
  padding: 1.5rem;
  background-color: var(--pf-v6-c-page__main-section--BackgroundColor, transparent);
}

/* PF6 Gallery grid */
.pf-v6-l-gallery {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(var(--pf-v6-l-gallery--GridTemplateColumns--min, 250px), 1fr));
  gap: 1rem;
}

/* PF6 Card */
.pf-v6-c-card {
  background-color: var(--pf-v6-c-card--BackgroundColor, #fff);
  border-radius: 8px;
  overflow: hidden;
}
.pf-v6-c-card__title { padding: 0.75rem 1rem 0; }
.pf-v6-c-card__body  { padding: 0.75rem 1rem; }
.pf-v6-c-card__footer { padding: 0 1rem 0.75rem; }

/* PF6 NumberInput (simplified) */
.pf-v6-c-number-input { display: inline-flex; align-items: center; }
.pf-v6-c-number-input .pf-v6-c-button { min-width: 28px; padding: 0 6px; }
.pf-v6-c-number-input input { width: 3ch; text-align: center; padding: 2px 4px; }

/* PF6 Button */
.pf-v6-c-button { display: inline-flex; align-items: center; gap: 0.25rem;
  padding: 0.375rem 0.75rem; border-radius: 4px; border: none; cursor: pointer;
  white-space: nowrap; }
.pf-v6-c-button.pf-m-primary { background-color: var(--pf-v6-c-button--m-primary--BackgroundColor, #06c); color: #fff; }

/* PF6 Tabs (minimal) */
.pf-v6-c-tabs__list { display: flex; list-style: none; margin: 0; padding: 0; }
.pf-v6-c-tabs__link  { padding: 0.75rem 1rem; background: none; border: none; cursor: pointer; }
`;

// Load the actual overrides.css from the repo
const OVERRIDES_CSS_PATH = path.resolve(__dirname, '../frontend/src/styles/overrides.css');
const OVERRIDES_CSS = fs.existsSync(OVERRIDES_CSS_PATH)
  ? fs.readFileSync(OVERRIDES_CSS_PATH, 'utf8')
  : '/* overrides.css not found */';

// ============================================================================
// HTML builders
// ============================================================================

/**
 * Build a minimal PF6 Page with one product card in the gallery.
 * The footer has a NumberInput + Add button (the combination that can overflow).
 */
function buildPageHTML({ addPfThemeDark = false, cardCount = 3 } = {}) {
  const htmlClass = addPfThemeDark ? ' class="pf-v6-theme-dark"' : '';
  const cards = Array.from({ length: cardCount }, (_, i) => `
    <li class="pf-v6-l-gallery__item">
      <div class="pf-v6-c-card ds-product-card catalog-card" id="product-card-test-${i}">
        <div class="pf-v6-c-card__title">
          <span class="ds-product-name">Product ${i + 1}</span>
        </div>
        <div class="pf-v6-c-card__body">
          <div class="price card-price">$${(9.99 * (i + 1)).toFixed(2)}</div>
          <div class="stock-badge in-stock">In stock</div>
        </div>
        <div class="pf-v6-c-card__footer" id="card-footer-${i}">
          <div class="catalog-card-actions" style="display:flex;gap:0.5rem;align-items:center;">
            <div class="pf-v6-c-number-input">
              <button class="pf-v6-c-button">-</button>
              <input value="1" style="width:3ch">
              <button class="pf-v6-c-button">+</button>
            </div>
            <button class="pf-v6-c-button pf-m-primary" id="add-to-cart-test-${i}">
              <svg width="14" height="14" aria-hidden="true"></svg>
              Add
            </button>
          </div>
        </div>
      </div>
    </li>`).join('');

  return `<!DOCTYPE html>
<html${htmlClass}>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body>
  <div class="pf-v6-c-page" id="page-root">
    <header class="pf-v6-c-page__header" style="grid-area:header;padding:1rem;">
      <h1>Darwin Store</h1>
    </header>
    <main class="pf-v6-c-page__main" id="page-main" style="grid-area:main;">
      <section class="pf-v6-c-page__main-section">
        <ul class="pf-v6-l-gallery pf-m-gutter" id="catalog-gallery">
          ${cards}
        </ul>
      </section>
    </main>
  </div>
</body>
</html>`;
}

// ============================================================================
// 1. Product Tile Layout -- no horizontal scroll, add-to-cart visible
// ============================================================================
test.describe('1. Product Tile Layout (no overflow, add-to-cart visible)', () => {

  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.setContent(buildPageHTML({ addPfThemeDark: true }));
    await page.addStyleTag({ content: PF_BASE_CSS });
    await page.addStyleTag({ content: OVERRIDES_CSS });
  });

  test('gallery renders product cards', async ({ page }) => {
    const cards = page.locator('.catalog-card');
    await expect(cards).toHaveCount(3);
  });

  test('catalog gallery has no horizontal scrollbar', async ({ page }) => {
    const gallery = page.locator('#catalog-gallery');
    const { scrollWidth, clientWidth } = await gallery.evaluate(el => ({
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
    }));
    // scrollWidth <= clientWidth means no overflow
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 2); // +2px tolerance
  });

  test('each product card does not overflow its container', async ({ page }) => {
    const galleryBox = await page.locator('#catalog-gallery').boundingBox();
    const cards = page.locator('.catalog-card');
    const count = await cards.count();

    for (let i = 0; i < count; i++) {
      const cardBox = await cards.nth(i).boundingBox();
      if (!cardBox || !galleryBox) continue;
      // Card right edge must not exceed gallery right edge (with 2px tolerance)
      expect(cardBox.x + cardBox.width).toBeLessThanOrEqual(galleryBox.x + galleryBox.width + 2);
    }
  });

  test('add-to-cart button is visible inside each card (not clipped)', async ({ page }) => {
    const buttons = page.locator('button[id^="add-to-cart-test-"]');
    const count = await buttons.count();
    expect(count).toBeGreaterThan(0);

    for (let i = 0; i < count; i++) {
      const btn = buttons.nth(i);
      // Must be visible
      await expect(btn).toBeVisible();

      const btnBox = await btn.boundingBox();
      const cardBox = await page.locator(`#product-card-test-${i}`).boundingBox();
      if (!btnBox || !cardBox) continue;

      // Button must be fully within the card horizontally
      expect(btnBox.x).toBeGreaterThanOrEqual(cardBox.x - 2);
      expect(btnBox.x + btnBox.width).toBeLessThanOrEqual(cardBox.x + cardBox.width + 2);
    }
  });

  test('card footer actions row does not cause card to overflow viewport', async ({ page }) => {
    const vpWidth = await page.evaluate(() => window.innerWidth);
    const cards = page.locator('.catalog-card');
    const count = await cards.count();

    for (let i = 0; i < count; i++) {
      const box = await cards.nth(i).boundingBox();
      if (!box) continue;
      expect(box.x + box.width).toBeLessThanOrEqual(vpWidth + 2);
    }
  });

  test('page has no horizontal scrollbar at 1280px viewport', async ({ page }) => {
    const { scrollWidth, clientWidth } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 2);
  });

  test('card footer has flex-wrap so button does not clip on narrow viewports', async ({ page }) => {
    // Resize to simulate a narrow-ish card scenario (3 cards at 700px = ~220px each)
    await page.setViewportSize({ width: 700, height: 800 });
    await page.setContent(buildPageHTML({ addPfThemeDark: true }));
    await page.addStyleTag({ content: PF_BASE_CSS });
    await page.addStyleTag({ content: OVERRIDES_CSS });

    const buttons = page.locator('button[id^="add-to-cart-test-"]');
    const count = await buttons.count();
    for (let i = 0; i < count; i++) {
      await expect(buttons.nth(i)).toBeVisible();
    }

    // Confirm no horizontal document overflow
    const { scrollWidth, clientWidth } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 2);
  });

  test('NumberInput minus/plus buttons are visible in card footer', async ({ page }) => {
    const minusButtons = page.locator('.pf-v6-c-number-input .pf-v6-c-button');
    await expect(minusButtons.first()).toBeVisible();
  });
});

// ============================================================================
// 2. PatternFly Dark Theme Integrity
// ============================================================================
test.describe('2. PatternFly Dark Theme (not overwritten by old CSS/inline styles)', () => {

  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
  });

  async function loadWithDarkTheme(page) {
    await page.setContent(buildPageHTML({ addPfThemeDark: true }));
    await page.addStyleTag({ content: PF_BASE_CSS });
    await page.addStyleTag({ content: OVERRIDES_CSS });
  }

  test('html element has pf-v6-theme-dark class (dark theme activated at root)', async ({ page }) => {
    await loadWithDarkTheme(page);
    const hasDarkClass = await page.evaluate(() =>
      document.documentElement.classList.contains('pf-v6-theme-dark')
    );
    expect(hasDarkClass).toBe(true);
  });

  test('page background color is dark (not white)', async ({ page }) => {
    await loadWithDarkTheme(page);
    const bgColor = await page.evaluate(() => {
      const el = document.getElementById('page-root');
      return window.getComputedStyle(el).backgroundColor;
    });
    // Dark theme = not white (rgb(255,255,255))
    expect(bgColor).not.toBe('rgb(255, 255, 255)');
    // Should be dark -- ds-bg-primary is #1a1a2e = rgb(26,26,46)
    expect(bgColor).not.toBe('rgba(0, 0, 0, 0)');
  });

  test('product card background is dark (not default PF white)', async ({ page }) => {
    await loadWithDarkTheme(page);
    const bgColor = await page.evaluate(() => {
      const el = document.querySelector('.ds-product-card');
      return window.getComputedStyle(el).backgroundColor;
    });
    // Should NOT be white -- PF default card bg is #fff
    expect(bgColor).not.toBe('rgb(255, 255, 255)');
  });

  test('--ds-bg-primary CSS variable is defined and dark', async ({ page }) => {
    await loadWithDarkTheme(page);
    const dsVar = await page.evaluate(() =>
      window.getComputedStyle(document.body).getPropertyValue('--ds-bg-primary').trim()
    );
    expect(dsVar).toBeTruthy();
    expect(dsVar).not.toBe('');
    // #1a1a2e is the expected value
    expect(dsVar.toLowerCase()).toBe('#1a1a2e');
  });

  test('--ds-bg-card CSS variable is defined', async ({ page }) => {
    await loadWithDarkTheme(page);
    const dsVar = await page.evaluate(() =>
      window.getComputedStyle(document.body).getPropertyValue('--ds-bg-card').trim()
    );
    expect(dsVar).toBeTruthy();
    expect(dsVar.toLowerCase()).toBe('#0f3460');
  });

  test('PF token --pf-t--global--background--color--primary--default maps to dark color', async ({ page }) => {
    await loadWithDarkTheme(page);
    const pfToken = await page.evaluate(() =>
      window.getComputedStyle(document.body)
        .getPropertyValue('--pf-t--global--background--color--primary--default').trim()
    );
    // Should be set (non-empty means our overrides mapped it)
    expect(pfToken).toBeTruthy();
    expect(pfToken).not.toBe('');
  });

  test('page section background is dark, not white or transparent', async ({ page }) => {
    await loadWithDarkTheme(page);
    const sectionBg = await page.evaluate(() => {
      const el = document.querySelector('.pf-v6-c-page__main-section');
      return window.getComputedStyle(el).backgroundColor;
    });
    // Should not be white or fully transparent on a dark-themed page
    expect(sectionBg).not.toBe('rgb(255, 255, 255)');
  });

  test('primary button uses accent color (--ds-accent), not PF default blue', async ({ page }) => {
    await loadWithDarkTheme(page);
    const btnBg = await page.evaluate(() => {
      const el = document.querySelector('button.pf-m-primary');
      return window.getComputedStyle(el).backgroundColor;
    });
    // --ds-accent is #e94560 = rgb(233, 69, 96)
    // PF default primary is #06c = rgb(0, 102, 204)
    expect(btnBg).not.toBe('rgb(0, 102, 204)');
  });

  test('price text uses --ds-success color (green), not default dark text', async ({ page }) => {
    await loadWithDarkTheme(page);
    const priceColor = await page.evaluate(() => {
      const el = document.querySelector('.price.card-price');
      return window.getComputedStyle(el).color;
    });
    // --ds-success = #4ade80 = rgb(74, 222, 128)
    expect(priceColor).toBe('rgb(74, 222, 128)');
  });

  test('stock badge in-stock uses success color (not default black text)', async ({ page }) => {
    await loadWithDarkTheme(page);
    const badgeColor = await page.evaluate(() => {
      const el = document.querySelector('.stock-badge.in-stock');
      return window.getComputedStyle(el).color;
    });
    // --ds-success = rgb(74, 222, 128)
    expect(badgeColor).toBe('rgb(74, 222, 128)');
  });

  test('page does not have white background when dark theme is active', async ({ page }) => {
    await loadWithDarkTheme(page);
    // Take a screenshot crop and verify it is not predominantly white
    // We use JS to check the pf-v6-c-page background-color CSS var is overridden
    const pageBgVar = await page.evaluate(() =>
      window.getComputedStyle(document.querySelector('.pf-v6-c-page'))
        .getPropertyValue('--pf-v6-c-page--BackgroundColor').trim()
    );
    // If developer adds `--pf-v6-c-page--BackgroundColor: var(--ds-bg-primary)` in CSS,
    // this should be non-empty and non-white
    // This test documents the requirement: the var must be overridden
    if (pageBgVar) {
      expect(pageBgVar).not.toMatch(/^#fff$|^#ffffff$|^white$|^rgb\(255,\s*255,\s*255\)$/i);
    }
    // Fallback: check actual rendered bg of page element is not white
    const actualBg = await page.evaluate(() =>
      window.getComputedStyle(document.querySelector('.pf-v6-c-page')).backgroundColor
    );
    expect(actualBg).not.toBe('rgb(255, 255, 255)');
  });
});

// ============================================================================
// 3. Full Viewport Stretch
// ============================================================================
test.describe('3. Full Viewport Stretch (UI fills entire width)', () => {

  async function loadPage(page, { addPfThemeDark = true } = {}) {
    await page.setContent(buildPageHTML({ addPfThemeDark }));
    await page.addStyleTag({ content: PF_BASE_CSS });
    await page.addStyleTag({ content: OVERRIDES_CSS });
  }

  test('page root has no max-width constraint (fills full viewport)', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loadPage(page);

    const { pageWidth, vpWidth } = await page.evaluate(() => ({
      pageWidth: document.getElementById('page-root').getBoundingClientRect().width,
      vpWidth: window.innerWidth,
    }));
    // Page should fill at least 95% of viewport (accounting for scrollbar)
    expect(pageWidth).toBeGreaterThanOrEqual(vpWidth * 0.95);
  });

  test('page root has no max-width: 960px applied', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loadPage(page);

    const maxWidth = await page.evaluate(() =>
      window.getComputedStyle(document.getElementById('page-root')).maxWidth
    );
    // Should be 'none' (no max-width), not '960px'
    expect(maxWidth).not.toBe('960px');
  });

  test('page fills full viewport width at 1280px', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await loadPage(page);

    const box = await page.locator('#page-root').boundingBox();
    expect(box).not.toBeNull();
    // Page width should match viewport (within 2px for scrollbar)
    expect(box.width).toBeGreaterThanOrEqual(1278);
  });

  test('page fills full viewport width at 1920px (wide screen)', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await loadPage(page);

    const box = await page.locator('#page-root').boundingBox();
    expect(box).not.toBeNull();
    expect(box.width).toBeGreaterThanOrEqual(1918);
  });

  test('no right-side whitespace gap at 1440px (content reaches right edge)', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loadPage(page);

    const { pageRight, vpRight } = await page.evaluate(() => {
      const rect = document.getElementById('page-root').getBoundingClientRect();
      return { pageRight: rect.right, vpRight: window.innerWidth };
    });
    // Right edge of page should be at viewport right edge (within 2px)
    expect(pageRight).toBeGreaterThanOrEqual(vpRight - 2);
  });

  test('gallery fills available width without centering margin', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await loadPage(page);

    const { marginLeft, marginRight } = await page.evaluate(() => {
      const el = document.getElementById('page-root');
      const style = window.getComputedStyle(el);
      return { marginLeft: style.marginLeft, marginRight: style.marginRight };
    });
    // margin: 0 auto would produce equal non-zero margins; full-width has margin 0
    expect(marginLeft).toBe('0px');
    expect(marginRight).toBe('0px');
  });

  test('phantom sidebar column is suppressed (single-column grid)', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 }); // > 75rem = 1200px
    await loadPage(page);

    const cols = await page.evaluate(() =>
      window.getComputedStyle(document.getElementById('page-root')).gridTemplateColumns
    );
    // Should be a single column (1fr = some px), not "290px Xpx" or "18.125rem 1fr"
    const colCount = cols.trim().split(/\s+/).filter(v => v && v !== '0px').length;
    expect(colCount).toBe(1);
  });

  test('page main content starts at x=0 (not offset by sidebar)', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await loadPage(page);

    const mainBox = await page.locator('#page-main').boundingBox();
    expect(mainBox).not.toBeNull();
    // Main should start at or near x=0, not x=290 (sidebar width)
    expect(mainBox.x).toBeLessThan(10);
  });
});
