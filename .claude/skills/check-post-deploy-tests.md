# Check Post-Deploy Test Reports

After an ArgoCD deployment, a PostSync Job runs Playwright smoke tests against
the live cluster and POSTs results to the chaos controller.

## Quick Check

```bash
# Get the latest test report
curl -s http://darwin-store-chaos:9000/api/test-reports/latest | python3 -m json.tool

# List all reports (newest first, max 50)
curl -s http://darwin-store-chaos:9000/api/test-reports | python3 -m json.tool
```

From outside the cluster, use the chaos route:

```bash
curl -s https://darwin-chaos-darwin.apps.cnv2.engineering.redhat.com/api/test-reports/latest
```

## Reading Results

Each report contains:

| Field        | Description                              |
|--------------|------------------------------------------|
| `id`         | Unique report ID                         |
| `suite`      | Always `post-deploy`                     |
| `total`      | Number of tests run                      |
| `passed`     | Tests that passed                        |
| `failed`     | Tests that failed                        |
| `skipped`    | Tests that were skipped                  |
| `duration_ms`| Total run duration in milliseconds       |
| `tests`      | Array of individual test case results    |
| `image_tag`  | Docker image tag that was deployed       |
| `git_sha`    | Git commit SHA of the deployment         |
| `received_at`| ISO timestamp when report was received   |

Each entry in `tests` has: `name`, `status` (passed/failed/skipped),
`duration_ms`, and `error` (failure message, if any).

## Pass / Fail

- `failed == 0` means the deployment is healthy.
- `failed > 0` means one or more smoke tests failed. Check the `tests` array
  for entries with `status: "failed"` and read their `error` field.

## What the Smoke Tests Cover

The post-deploy suite (`tests/post-deploy/smoke.spec.js`) verifies:

- **Frontend**: homepage loads, static assets served
- **Backend API**: /health, /products, /orders, /customers, /alerts, /invoices
- **Chaos Controller**: /api/status, /api/test-reports, UI page

## UI

The chaos controller UI (port 9000) has a **Test Reports** tab that displays
all stored reports with pass/fail badges and expandable per-test details.

## Troubleshooting

If no reports exist (`"status": "no_reports"`):
1. Check if `postDeployTests.enabled` is `true` in `helm/values.yaml`
2. Check if the PostSync Job ran: `kubectl get jobs -l app=darwin-store-tests`
3. Check Job logs: `kubectl logs job/darwin-store-post-deploy-tests`
