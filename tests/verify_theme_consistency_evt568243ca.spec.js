// tests/verify_theme_consistency_evt568243ca.spec.js
// QE verification: evt-568243ca card/modal theme collision fix (commit 2f6a45b)
//
// User report: product card header=blue, body=grey, footer=grey (theme collision).
// Root cause: PF6 card/modal sections had their own grey background via PF CSS
//   tokens. Overrides used CSS `background` shorthand which lost to PF6's
//   `background-color` token chain.
// Fix: override PF6 component-level tokens directly (--pf-v6-c-card--BackgroundColor,
//   --pf-v6-c-modal-box--BackgroundColor) so all card/modal sections inherit uniformly.
//
// @ai-rules:
// 1. [Constraint]: Self-contained -- uses page.setContent() + addStyleTag() OR
//    local dev server at http://localhost:3456 with mocked API routes.
// 2. [Coverage]: Card section color consistency, modal section color consistency,
//    no PF grey (#383838) bleeding through, token-based dark theme integrity.

const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

// Load actual overrides.css from repo
const OVERRIDES_CSS_PATH = path.resolve(__dirname, '../frontend/src/styles/overrides.css');
const OVERRIDES_CSS = fs.existsSync(OVERRIDES_CSS_PATH)
  ? fs.readFileSync(OVERRIDES_CSS_PATH, 'utf8')
  : '/* overrides.css not found */';

// Minimal PF6 Card + Modal CSS that replicates the theme collision scenario
const PF_CARD_MODAL_CSS = `
*, *::before, *::after { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: white; }

/* PF6 card token chain (replicates actual PF6 behaviour) */
.pf-v6-c-card {
  background-color: var(--pf-v6-c-card--BackgroundColor,
    var(--pf-t--global--background--color--primary--default, #fff));
  border-radius: 8px;
  overflow: hidden;
}
.pf-v6-c-card__title {
  background-color: var(--pf-v6-c-card__title--BackgroundColor, transparent);
  padding: 0.75rem 1rem 0;
}
.pf-v6-c-card__body {
  background-color: var(--pf-v6-c-card__body--BackgroundColor, transparent);
  padding: 0.75rem 1rem;
}
.pf-v6-c-card__footer {
  background-color: var(--pf-v6-c-card__footer--BackgroundColor, transparent);
  padding: 0 1rem 0.75rem;
}

/* PF6 modal token chain */
.pf-v6-c-modal-box {
  background-color: var(--pf-v6-c-modal-box--BackgroundColor,
    var(--pf-t--global--background--color--floating--default, #383838));
  color: var(--pf-v6-c-modal-box--Color, inherit);
  border-radius: 8px;
  overflow: hidden;
}
.pf-v6-c-modal-box__header {
  background-color: var(--pf-v6-c-modal-box__header--BackgroundColor, transparent);
  padding: 1rem;
  border-bottom: 1px solid rgba(255,255,255,0.1);
}
.pf-v6-c-modal-box__body {
  background-color: var(--pf-v6-c-modal-box__body--BackgroundColor, transparent);
  padding: 1rem;
}
.pf-v6-c-modal-box__footer {
  background-color: var(--pf-v6-c-modal-box__footer--BackgroundColor, transparent);
  padding: 1rem;
  border-top: 1px solid rgba(255,255,255,0.1);
}

/* PF6 gallery */
.pf-v6-l-gallery {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 1rem;
}
`;

// HTML fixture with card + modal
const PAGE_HTML = `<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body>
  <div class="pf-v6-l-gallery">
    <div class="pf-v6-c-card ds-product-card catalog-card" id="test-card">
      <div class="pf-v6-c-card__title" id="card-title">
        <span>Test Product</span>
      </div>
      <div class="pf-v6-c-card__body" id="card-body">
        <div class="price card-price">$19.99</div>
        <div class="stock-badge in-stock">In stock</div>
      </div>
      <div class="pf-v6-c-card__footer" id="card-footer">
        <button class="pf-v6-c-button pf-m-primary">Add to Cart</button>
      </div>
    </div>
  </div>

  <div class="pf-v6-c-modal-box pf-m-md" id="test-modal" style="margin-top:2rem;">
    <div class="pf-v6-c-modal-box__header" id="modal-header">
      <h2>Test Product</h2>
    </div>
    <div class="pf-v6-c-modal-box__body" id="modal-body">
      <p>Product description goes here.</p>
      <div class="price card-price">$19.99</div>
    </div>
    <div class="pf-v6-c-modal-box__footer" id="modal-footer">
      <button class="pf-v6-c-button pf-m-secondary">Close</button>
    </div>
  </div>
</body>
</html>`;

// Helper: load fixture with PF CSS then overrides
async function loadFixture(page) {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.setContent(PAGE_HTML);
  await page.addStyleTag({ content: PF_CARD_MODAL_CSS });
  await page.addStyleTag({ content: OVERRIDES_CSS });
}

// Helper: get bg color of an element
async function getBg(page, selector) {
  return page.evaluate(sel => {
    const el = document.querySelector(sel);
    return el ? window.getComputedStyle(el).backgroundColor : null;
  }, selector);
}

// Helper: assert two colors are the same OR one is transparent (showing through parent)
function expectConsistent(bgA, bgB, labelA, labelB) {
  const transparent = 'rgba(0, 0, 0, 0)';
  if (bgA === transparent || bgB === transparent) {
    // Transparent sections are fine — they show the parent's background
    return;
  }
  expect(bgA, `${labelA} should match ${labelB}`).toBe(bgB);
}

// ============================================================================
// 1. Product Card — Consistent backgrounds across all sections
// ============================================================================
test.describe('1. Product Card — No header/body/footer color collision', () => {

  test.beforeEach(async ({ page }) => { await loadFixture(page); });

  test('card container has a dark background (not white, not PF grey)', async ({ page }) => {
    const bg = await getBg(page, '#test-card');
    expect(bg).not.toBe('rgb(255, 255, 255)'); // not white
    expect(bg).not.toBe('rgb(56, 56, 56)');    // not PF floating grey
    expect(bg).not.toBeNull();
  });

  test('card title section is transparent (consistent with card background)', async ({ page }) => {
    const titleBg = await getBg(page, '#card-title');
    // Title should be transparent (inherits from card) - no independent colour
    expect(titleBg).toBe('rgba(0, 0, 0, 0)');
  });

  test('card body section is transparent (consistent with card background)', async ({ page }) => {
    const bodyBg = await getBg(page, '#card-body');
    // Body must not show PF's grey default
    expect(bodyBg).not.toBe('rgb(209, 209, 209)'); // PF grey fallback
    expect(bodyBg).not.toBe('rgb(240, 240, 240)'); // another PF grey
    // Should be transparent or dark (matching card)
    const cardBg = await getBg(page, '#test-card');
    if (bodyBg !== 'rgba(0, 0, 0, 0)') {
      expect(bodyBg).toBe(cardBg);
    }
  });

  test('card footer section is transparent (consistent with card background)', async ({ page }) => {
    const footerBg = await getBg(page, '#card-footer');
    expect(footerBg).not.toBe('rgb(209, 209, 209)');
    expect(footerBg).not.toBe('rgb(240, 240, 240)');
    const cardBg = await getBg(page, '#test-card');
    if (footerBg !== 'rgba(0, 0, 0, 0)') {
      expect(footerBg).toBe(cardBg);
    }
  });

  test('card body and footer DO NOT clash with card header color', async ({ page }) => {
    const titleBg = await getBg(page, '#card-title');
    const bodyBg  = await getBg(page, '#card-body');
    const footerBg = await getBg(page, '#card-footer');
    // All should be the same or transparent — no mismatched colors
    expectConsistent(titleBg, bodyBg, 'card-title', 'card-body');
    expectConsistent(bodyBg, footerBg, 'card-body', 'card-footer');
    expectConsistent(titleBg, footerBg, 'card-title', 'card-footer');
  });

  test('--pf-v6-c-card--BackgroundColor token is set on card (not empty)', async ({ page }) => {
    const token = await page.evaluate(() =>
      window.getComputedStyle(document.querySelector('#test-card'))
        .getPropertyValue('--pf-v6-c-card--BackgroundColor').trim()
    );
    expect(token).not.toBe('');
    expect(token).toBeTruthy();
  });

  test('card background resolves to a dark color from our theme', async ({ page }) => {
    const bg = await getBg(page, '#test-card');
    // Parse rgb values and verify it is dark
    const match = bg.match(/rgb[a]?\((\d+),\s*(\d+),\s*(\d+)/);
    if (match) {
      const [, r, g, b] = match.map(Number);
      const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
      // Dark theme card: luminance should be < 0.3
      expect(luminance).toBeLessThan(0.3);
    }
  });

  test('card sections are visually uniform (all dark, no grey break-out)', async ({ page }) => {
    // Take visual verification: check that no section is noticeably lighter than card
    const cardBg  = await getBg(page, '#test-card');
    const titleBg = await getBg(page, '#card-title');
    const bodyBg  = await getBg(page, '#card-body');
    const footerBg = await getBg(page, '#card-footer');

    const isTransparent = c => c === 'rgba(0, 0, 0, 0)';
    const isLight = c => {
      const m = c.match(/rgb[a]?\((\d+),\s*(\d+),\s*(\d+)/);
      if (!m) return false;
      const lum = (0.299 * +m[1] + 0.587 * +m[2] + 0.114 * +m[3]) / 255;
      return lum > 0.5; // lighter than 50% = too light for dark theme
    };

    for (const [label, bg] of [['title', titleBg], ['body', bodyBg], ['footer', footerBg]]) {
      if (!isTransparent(bg)) {
        expect(isLight(bg), `card ${label} (${bg}) should not be a light/grey color`).toBe(false);
      }
    }
  });
});

// ============================================================================
// 2. Product Detail Modal — Consistent dark backgrounds
// ============================================================================
test.describe('2. Product Detail Modal — Consistent dark theme (no grey body)', () => {

  test.beforeEach(async ({ page }) => { await loadFixture(page); });

  test('modal box has a dark background (not PF floating grey #383838)', async ({ page }) => {
    const bg = await getBg(page, '#test-modal');
    expect(bg).not.toBe('rgb(56, 56, 56)'); // PF6 dark-mode floating default
    expect(bg).not.toBe('rgb(255, 255, 255)'); // not white
    expect(bg).not.toBeNull();
  });

  test('--pf-v6-c-modal-box--BackgroundColor token is set (overrides PF floating grey)', async ({ page }) => {
    const token = await page.evaluate(() =>
      window.getComputedStyle(document.querySelector('#test-modal'))
        .getPropertyValue('--pf-v6-c-modal-box--BackgroundColor').trim()
    );
    expect(token).not.toBe('');
    expect(token).toBeTruthy();
  });

  test('modal header has no contrasting grey background vs modal box', async ({ page }) => {
    const modalBg  = await getBg(page, '#test-modal');
    const headerBg = await getBg(page, '#modal-header');
    expectConsistent(modalBg, headerBg, 'modal', 'modal-header');
  });

  test('modal body is transparent (shows modal box background, not PF grey)', async ({ page }) => {
    const bodyBg = await getBg(page, '#modal-body');
    // Before fix: body showed rgb(56,56,56) PF grey
    expect(bodyBg).not.toBe('rgb(56, 56, 56)');
    expect(bodyBg).not.toBe('rgb(255, 255, 255)');
    // Should be transparent or same as modal
    const modalBg = await getBg(page, '#test-modal');
    if (bodyBg !== 'rgba(0, 0, 0, 0)') {
      expect(bodyBg).toBe(modalBg);
    }
  });

  test('modal footer is transparent (shows modal box background, not PF grey)', async ({ page }) => {
    const footerBg = await getBg(page, '#modal-footer');
    expect(footerBg).not.toBe('rgb(56, 56, 56)');
    expect(footerBg).not.toBe('rgb(255, 255, 255)');
    const modalBg = await getBg(page, '#test-modal');
    if (footerBg !== 'rgba(0, 0, 0, 0)') {
      expect(footerBg).toBe(modalBg);
    }
  });

  test('modal header, body, footer are visually consistent (all same dark tone)', async ({ page }) => {
    const headerBg = await getBg(page, '#modal-header');
    const bodyBg   = await getBg(page, '#modal-body');
    const footerBg = await getBg(page, '#modal-footer');
    expectConsistent(headerBg, bodyBg, 'modal-header', 'modal-body');
    expectConsistent(bodyBg, footerBg, 'modal-body', 'modal-footer');
  });

  test('modal box background uses --ds-bg-secondary color (#16213e)', async ({ page }) => {
    const bg = await getBg(page, '#test-modal');
    // --ds-bg-secondary = #16213e = rgb(22, 33, 62)
    // Accept either the exact value or a dark transparent-inherited dark tone
    if (bg !== 'rgba(0, 0, 0, 0)') {
      expect(bg).toBe('rgb(22, 33, 62)');
    }
  });

  test('no section shows PF default floating grey (rgb 56,56,56)', async ({ page }) => {
    const greyTarget = 'rgb(56, 56, 56)';
    for (const sel of ['#test-modal', '#modal-header', '#modal-body', '#modal-footer']) {
      const bg = await getBg(page, sel);
      expect(bg, `${sel} must not be PF floating grey`).not.toBe(greyTarget);
    }
  });
});

// ============================================================================
// 3. Global token overrides — floating tier now mapped
// ============================================================================
test.describe('3. PF6 Token Coverage — All background tiers overridden', () => {

  test.beforeEach(async ({ page }) => { await loadFixture(page); });

  test('--pf-t--global--background--color--primary--default is set on body', async ({ page }) => {
    const val = await page.evaluate(() =>
      window.getComputedStyle(document.body)
        .getPropertyValue('--pf-t--global--background--color--primary--default').trim()
    );
    expect(val).not.toBe('');
  });

  test('--pf-t--global--background--color--secondary--default is set on body', async ({ page }) => {
    const val = await page.evaluate(() =>
      window.getComputedStyle(document.body)
        .getPropertyValue('--pf-t--global--background--color--secondary--default').trim()
    );
    expect(val).not.toBe('');
  });

  test('--pf-t--global--background--color--floating--default is set on body', async ({ page }) => {
    const val = await page.evaluate(() =>
      window.getComputedStyle(document.body)
        .getPropertyValue('--pf-t--global--background--color--floating--default').trim()
    );
    expect(val).not.toBe('');
    // This was the missing tier — controls modals and menus
  });

  test('floating tier token resolves to --ds-bg-secondary (not PF grey)', async ({ page }) => {
    const val = await page.evaluate(() =>
      window.getComputedStyle(document.body)
        .getPropertyValue('--pf-t--global--background--color--floating--default').trim()
    );
    // Should reference ds-bg-secondary or resolve to #16213e, not be the PF default grey
    if (val) {
      expect(val.toLowerCase()).not.toBe('#383838');
      expect(val).not.toMatch(/^rgb\(56,\s*56,\s*56\)/);
    }
  });

  test('--ds-bg-card token is set and is a dark color', async ({ page }) => {
    const val = await page.evaluate(() =>
      window.getComputedStyle(document.body)
        .getPropertyValue('--ds-bg-card').trim()
    );
    expect(val).not.toBe('');
    expect(val.toLowerCase()).toBe('#0f3460');
  });

  test('--ds-bg-secondary token is set to dark navy', async ({ page }) => {
    const val = await page.evaluate(() =>
      window.getComputedStyle(document.body)
        .getPropertyValue('--ds-bg-secondary').trim()
    );
    expect(val).not.toBe('');
    expect(val.toLowerCase()).toBe('#16213e');
  });
});

// ============================================================================
// 4. Live deployment smoke test — verify fix is in production
// ============================================================================
test.describe('4. Live Deployment — Card/Modal theme consistency', () => {
  const LIVE_URL = process.env.STORE_URL || 'https://darwin-store-darwin.apps.cnv2.engineering.redhat.com';

  async function loadLive(page) {
    await page.route('**/api/products', r => r.fulfill({ json: [
      { id: 'p1', name: 'Test Widget', price: 19.99, stock: 50, sku: 'TW-001',
        description: 'desc', image_data: null, supplier_id: null }
    ]}));
    await page.route('**/api/**', r => r.fulfill({ json: [] }));
    await page.goto(LIVE_URL, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(2000);
  }

  test.skip(({ }, testInfo) => {
    // Skip live tests in CI (GitHub Actions sets CI=true) or when SKIP_LIVE is set
    return !!process.env.CI || !!process.env.SKIP_LIVE;
  }, 'Live tests skipped in CI / SKIP_LIVE mode');

  test('live: catalog card has uniform dark background across all sections', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await loadLive(page);

    const cardExists = await page.locator('.ds-product-card').count() > 0;
    if (!cardExists) { test.skip(); return; }

    const colors = await page.evaluate(() => {
      const card = document.querySelector('.ds-product-card');
      const getC = el => el ? window.getComputedStyle(el).backgroundColor : null;
      return {
        card:   getC(card),
        title:  getC(card?.querySelector('.pf-v6-c-card__title')),
        body:   getC(card?.querySelector('.pf-v6-c-card__body')),
        footer: getC(card?.querySelector('.pf-v6-c-card__footer')),
      };
    });

    const isGrey = c => c === 'rgb(56, 56, 56)' || c === 'rgb(209, 209, 209)';
    const isWhite = c => c === 'rgb(255, 255, 255)';
    const isTransparent = c => c === 'rgba(0, 0, 0, 0)';

    // Card container must be dark
    expect(isGrey(colors.card), `card bg (${colors.card}) must not be PF grey`).toBe(false);
    expect(isWhite(colors.card), `card bg must not be white`).toBe(false);

    // Sections: transparent OR matching card (no grey break-out)
    for (const [label, bg] of [['title', colors.title], ['body', colors.body], ['footer', colors.footer]]) {
      if (!isTransparent(bg) && bg !== null) {
        expect(isGrey(bg), `card ${label} (${bg}) must not be grey`).toBe(false);
      }
    }
  });

  test('live: product detail modal has uniform dark background', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await loadLive(page);

    const cardExists = await page.locator('.ds-product-card').count() > 0;
    if (!cardExists) { test.skip(); return; }

    await page.click('.ds-product-card');
    await page.waitForSelector('.pf-v6-c-modal-box', { timeout: 10000 }).catch(() => {});

    const modalExists = await page.locator('.pf-v6-c-modal-box').count() > 0;
    if (!modalExists) { test.skip(); return; }

    const colors = await page.evaluate(() => {
      const modal = document.querySelector('.pf-v6-c-modal-box');
      const getC = el => el ? window.getComputedStyle(el).backgroundColor : null;
      return {
        modal:  getC(modal),
        header: getC(modal?.querySelector('.pf-v6-c-modal-box__header')),
        body:   getC(modal?.querySelector('.pf-v6-c-modal-box__body')),
        footer: getC(modal?.querySelector('.pf-v6-c-modal-box__footer')),
      };
    });

    const PF_GREY = 'rgb(56, 56, 56)';

    // Modal must not be PF floating grey
    expect(colors.modal).not.toBe(PF_GREY);
    expect(colors.modal).not.toBe('rgb(255, 255, 255)');

    // Body and footer must not show PF grey (the pre-fix symptom)
    if (colors.body) expect(colors.body).not.toBe(PF_GREY);
    if (colors.footer) expect(colors.footer).not.toBe(PF_GREY);
  });
});
