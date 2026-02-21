# Darwin Store -- Testing Guide

Quality gate for the Darwin Store application. Tests run automatically in CI before agent branches are auto-merged to main.

## Test Inventory

| File | Category | What It Tests | CI-Gated? |
| ---- | -------- | ------------- | --------- |
| `test_model.py` | Python unit | Pydantic model field existence and defaults | Yes |
| `test_html_structure.py` | Python unit | Static HTML structure (tabs, forms, description fields) | Yes |
| `test_order_history.py` | Python unit | `GET /orders` endpoint with mocked DB | Yes |
| `test_orders.py` | Python unit | Order CRUD operations with mocked DB | Yes |
| `test_orders_qe.py` | Python unit | `POST /orders` atomic stock update, rollback, error handling | Yes |
| `test_orders_uuid_fix.py` | Python unit | UUID cast fix for `order_id = ANY(%s::uuid[])` | Yes |
| `test_order_status.py` | Python unit | Order status transitions (pending, processing, shipped, delivered) | Yes |
| `test_uuid_cast_fix.py` | Python unit | UUID object handling from PostgreSQL | Yes |
| `test_customers_qe.py` | Python unit | Customer CRUD and email uniqueness | Yes |
| `test_redesign.py` | Python unit | Product model and route redesign validation | Yes |
| `test_unassigned_orders.py` | Python unit | Unassigned/legacy order management | Yes |
| `verify_customers_api.py` | Python unit | Customer API endpoint verification | Yes |
| `test_dependency_filter.py` | Python unit | DarwinClient topology filtering (SKIPPED -- `darwin_client.py` deprecated) | No |
| `test_darwin_client_repro.py` | Python unit | DarwinClient bug repro (SKIPPED -- `darwin_client.py` deprecated) | No |
| `test_shopping_cart.spec.js` | Playwright (self-contained) | Cart: add, update quantity, remove, badge | Yes |
| `verify_ui.spec.js` | Playwright (self-contained) | Tab structure, catalog cards, inventory table, description fields | Yes |
| `verify_checkout.spec.js` | Playwright (self-contained) | Checkout flow with mocked API | Yes |
| `verify_frontend_customers.spec.js` | Playwright (self-contained) | Customer management UI | Yes |
| `verify_shopping_cart.spec.js` | Playwright (self-contained) | Shopping cart full flow | Yes |
| `verify_unassigned_orders_ui.spec.js` | Playwright (self-contained) | Unassigned orders UI | Yes |
| `verify_ui_mocked.spec.js` | Playwright (server-dependent) | Full checkout flow (needs live server) | No |
| `verify_order_history.spec.js` | Playwright (server-dependent) | Order history UI (needs live server) | No |

## Running Locally

### Python Tests

```bash
pip install -r requirements-test.txt
python -m pytest tests/test_model.py tests/test_html_structure.py \
  tests/test_order_history.py tests/test_orders_qe.py \
  tests/test_orders_uuid_fix.py tests/test_uuid_cast_fix.py -v
```

### Playwright Tests (Self-Contained)

These mock API routes and inject HTML inline -- no server needed.

```bash
npm ci
npx playwright install --with-deps chromium
npm test
```

### Playwright Tests (Server-Dependent)

These navigate to `localhost:8081` and require a running static file server.

```bash
# Terminal 1: Start the static server
python -m http.server 8081 --directory src/app/static &

# Terminal 2: Run the tests
npx playwright test tests/verify_ui_mocked.spec.js tests/verify_order_history.spec.js
```

## CI Quality Gate

The workflow `.github/workflows/ci-branch.yaml` runs three parallel jobs on every push to `feat/**`:

1. **validate** -- Docker image builds, Helm tag conflict check
2. **test-python** -- `pytest` with explicit file list (6 files)
3. **test-playwright** -- Self-contained Playwright tests (2 specs, Chromium only)

All three must pass before the **auto-merge** job creates a PR and merges to main.

If any test fails, the merge is blocked. The agent's branch stays open until fixes are pushed.

## Writing New Tests

### Python Tests

- Name files `test_*.py` in `tests/`
- `conftest.py` adds `src/` to `sys.path` -- no manual path hacks needed
- Mock the DB connection pool: `@patch("app.main.SimpleConnectionPool")`
- Use `with TestClient(app) as client:` inside each test function (not at module level)
- Add the new file to the explicit list in `ci-branch.yaml` `test-python` job

### Playwright Tests

- Self-contained tests: mock routes via `page.route()` and serve HTML inline
- Server-dependent tests: navigate to `localhost:8081`
- Only self-contained tests are CI-gated (add to `package.json` `test` script)
- Config: `playwright.config.js` restricts to Chromium only

## Known Gaps

- `test_dependency_filter.py` is excluded from CI because `darwin_client.py` was removed (deprecated). The test remains for reference until the DarwinClient module is permanently removed or replaced.
- `verify_ui_mocked.spec.js` and `verify_order_history.spec.js` require a live server and are not CI-gated. These are local verification tests only.
