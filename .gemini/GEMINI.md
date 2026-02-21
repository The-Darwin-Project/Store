# Darwin Store -- Project Context

## Project

Darwin Store is a FastAPI + PostgreSQL test-subject application with chaos injection. It is the target application that Darwin's autonomous agents observe, diagnose, and remediate.

## Architecture

Two processes run in the same container:

- **Store API** (port 8080): Product CRUD, orders, customers. FastAPI with PostgreSQL.
- **Chaos Controller** (port 9000): Injects CPU burn, memory pressure, latency, and error rate.
- **State sharing**: `/tmp/chaos_state.json` via atomic `tempfile` + `os.replace` writes.

Discovery is passive -- the BlackBoard K8s Observer reads `darwin.io/*` annotations on the Deployment. No push telemetry.

## API Surface

| Endpoint | Method | Notes |
| -------- | ------ | ----- |
| `/products` | GET, POST | List / create products |
| `/products/{id}` | GET, PUT, PATCH, DELETE | PUT = full replace (all fields required), PATCH = partial update |
| `/orders` | GET, POST | GET returns orders with items. POST validates stock atomically |
| `/orders/{id}` | DELETE | Deletes order and items |
| `/customers` | GET, POST | Email uniqueness enforced (409 on duplicate) |
| `/api/settings` | POST (port 9000) | Single mutation endpoint for all chaos settings |

Key patterns:
- Orders use `UPDATE ... SET stock = stock - %s WHERE stock >= %s` for atomic deduction
- Order items query uses `::uuid[]` cast to avoid PostgreSQL type mismatch
- PUT overwrites all fields including `image_data`. PATCH uses `model_dump(exclude_unset=True)`

## Database

PostgreSQL with `SimpleConnectionPool`. Tables: `products`, `customers`, `orders`, `order_items`. Schema auto-created on startup with migration support.

## Code Conventions

- Python, FastAPI, Pydantic models
- Every file has `@ai-rules` shebang at top (read these before editing)
- Target max 100 lines per file
- Structured logging, debug logs opt-in via `DEBUG` env var

## Testing

See `TESTING.md` for the full QE guide.

- **Python**: `pip install -r requirements-test.txt && pytest tests/ -v`
- **Playwright**: `npm ci && npx playwright install chromium && npm test`
- Mock DB with `@patch("app.main.SimpleConnectionPool")`
- Self-contained Playwright tests mock routes inline (no server needed)

## CI/CD

- `ci-branch.yaml`: Runs pytest + Playwright before auto-merge to main on `feat/**` branches
- `build-push.yaml`: Builds Docker image and pushes to GHCR on main push, updates `helm/values.yaml` tag
- Dockerfile uses `registry.access.redhat.com/ubi9/ubi:latest`

## Forbidden

- Do NOT modify `helm/values.yaml` image tag -- CI manages this
- Do NOT modify `.github/workflows/` files -- SysAdmin's domain
- Do NOT force push (`git push --force`)
- Do NOT modify Dockerfile unless explicitly in the plan
- Do NOT add runtime dependencies to `requirements-test.txt` (test-only deps)

## Environment Variables

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `DB_HOST` | (none) | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `darwin` | Database name |
| `DB_USER` | `postgres` | Database user |
| `DB_PASSWORD` | (none) | Database password |
| `CHAOS_MODE` | `disabled` | Gates ChaosMiddleware (set `enabled` to activate) |
| `SERVICE_NAME` | `darwin-store` | Service name in telemetry |
