# Darwin Store

FastAPI + PostgreSQL test-subject app with chaos injection. Target application for Darwin autonomous agents.

## Quick Reference

```bash
# Run locally
pip install -r requirements.txt
uvicorn src.app.main:app --port 8080 &
uvicorn src.chaos.main:app --port 9000 &

# Run tests
pip install -r requirements-test.txt
pytest tests/ -v
npm ci && npx playwright install chromium && npm test
```

## Architecture

- **Store API** (:8080) -- Product CRUD, orders, customers. FastAPI + PostgreSQL.
- **Chaos Controller** (:9000) -- CPU burn, memory pressure, latency, error injection.
- **State** -- Cross-process via `/tmp/chaos_state.json` (atomic writes).
- **Discovery** -- Passive via `darwin.io/*` K8s annotations. No push telemetry.

## API Patterns

- `PUT /products/{id}` = full replace (all fields required, overwrites `image_data`)
- `PATCH /products/{id}` = partial update (`model_dump(exclude_unset=True)`)
- `POST /orders` = atomic stock deduction (`UPDATE ... WHERE stock >= %s`)
- `GET /orders` = items query uses `::uuid[]` cast for type safety
- `POST /api/settings` (port 9000) = single mutation endpoint for all chaos settings

## Database

PostgreSQL, `SimpleConnectionPool`. Tables: `products`, `customers`, `orders`, `order_items`.

## Code Conventions

- Every source file has `@ai-rules` shebang -- read before editing
- Max 100 lines per file
- Pydantic models: Create/Update/Read split (ProductCreate, ProductUpdate, Product)
- ProductUpdate fields are all Optional for partial updates

## Testing

Full guide: `TESTING.md`

- Python: pytest with `@patch("app.main.SimpleConnectionPool")` for DB mocking
- Playwright: self-contained tests mock routes inline, no server needed
- `conftest.py` handles `sys.path` -- no manual path hacks in test files
- New test files must be added to explicit list in `ci-branch.yaml`

## CI/CD

- `feat/fix/chore/refactor` branches with source changes: `ci-branch.yaml` runs pytest + Playwright, then auto-merges
- `feat/fix/chore/refactor` branches with GitOps-only changes (helm/docs): `ci-branch-gitops.yaml` auto-merges without tests
- `main` pushes: `build-push.yaml` builds image, pushes to GHCR, updates Helm tag

## Forbidden

- Do NOT modify `helm/values.yaml` image tags (CI-managed via build-push.yaml)
- Operational fields (replicaCount, resources, config) in values.yaml CAN be modified via feature branches
- Do NOT modify `.github/workflows/` (SysAdmin's domain)
- Do NOT force push
- Do NOT add runtime deps to `requirements-test.txt`
- Do NOT create module-level `TestClient(app)` -- use `with TestClient(app) as client:` inside test functions

## Environment Variables

- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` -- PostgreSQL connection
- `CHAOS_MODE` -- `disabled` (default) or `enabled` to activate ChaosMiddleware
- `SERVICE_NAME` -- `darwin-store` (default)
