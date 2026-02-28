#!/bin/bash
# tests/post-deploy/run-tests.sh
# Runs post-deploy smoke tests and POSTs results to the chaos controller.
#
# Environment variables (set by the Helm Job):
#   STORE_URL    — frontend service URL   (default: http://darwin-store-frontend:8080)
#   BACKEND_URL  — backend API URL        (default: http://darwin-store-backend:8080)
#   CHAOS_URL    — chaos controller URL   (default: http://darwin-store-chaos:9000)
#   IMAGE_TAG    — deployed image tag     (optional)
#   GIT_SHA      — git commit SHA         (optional)

set -euo pipefail

CHAOS_URL="${CHAOS_URL:-http://darwin-store-chaos:9000}"
TEST_DIR="$(dirname "$0")"

echo "=== Post-deploy smoke tests ==="
echo "STORE_URL:   ${STORE_URL:-http://darwin-store-frontend:8080}"
echo "BACKEND_URL: ${BACKEND_URL:-http://darwin-store-backend:8080}"
echo "CHAOS_URL:   ${CHAOS_URL}"
echo ""

# Run Playwright tests and capture JSON output
RESULTS_FILE="/tmp/test-results.json"
npx playwright test \
  --config="${TEST_DIR}/playwright.config.js" \
  --reporter=json \
  > "${RESULTS_FILE}" 2>&1 || true

# Parse results and build report payload
if [ -f "${RESULTS_FILE}" ] && python3 -c "import json; json.load(open('${RESULTS_FILE}'))" 2>/dev/null; then
  REPORT=$(python3 -c "
import json, sys

with open('${RESULTS_FILE}') as f:
    data = json.load(f)

suites = data.get('suites', [])
tests = []
passed = failed = skipped = 0
total_duration = 0

for suite in suites:
    for spec in suite.get('specs', []):
        for result in spec.get('tests', []):
            for r in result.get('results', []):
                status = r.get('status', 'unknown')
                duration = r.get('duration', 0)
                name = spec.get('title', 'unknown')
                error = None
                if status == 'failed':
                    error_obj = r.get('error', {})
                    error = error_obj.get('message', str(error_obj)) if error_obj else None
                tests.append({
                    'name': name,
                    'status': status,
                    'duration_ms': duration,
                    'error': error
                })
                total_duration += duration
                if status == 'passed': passed += 1
                elif status == 'failed': failed += 1
                elif status == 'skipped': skipped += 1

report = {
    'suite': 'post-deploy',
    'total': passed + failed + skipped,
    'passed': passed,
    'failed': failed,
    'skipped': skipped,
    'duration_ms': total_duration,
    'tests': tests,
    'image_tag': '${IMAGE_TAG:-}' or None,
    'git_sha': '${GIT_SHA:-}' or None,
}
print(json.dumps(report))
")
else
  # Tests crashed or produced no JSON — build a minimal failure report
  echo "WARNING: Playwright did not produce valid JSON output"
  REPORT=$(python3 -c "
import json
report = {
    'suite': 'post-deploy',
    'total': 1,
    'passed': 0,
    'failed': 1,
    'skipped': 0,
    'duration_ms': 0,
    'tests': [{'name': 'test-runner', 'status': 'failed', 'duration_ms': 0, 'error': 'Playwright failed to produce JSON results'}],
    'image_tag': '${IMAGE_TAG:-}' or None,
    'git_sha': '${GIT_SHA:-}' or None,
}
print(json.dumps(report))
")
fi

echo ""
echo "=== Posting results to chaos controller ==="
echo "${REPORT}" | python3 -m json.tool

HTTP_CODE=$(curl -s -o /tmp/post-response.txt -w "%{http_code}" \
  -X POST "${CHAOS_URL}/api/test-reports" \
  -H "Content-Type: application/json" \
  -d "${REPORT}")

echo "Response (${HTTP_CODE}):"
cat /tmp/post-response.txt
echo ""

if [ "${HTTP_CODE}" = "201" ]; then
  echo "=== Results posted successfully ==="
else
  echo "WARNING: Failed to post results (HTTP ${HTTP_CODE})"
fi

# Exit with appropriate code based on test results
FAILED=$(echo "${REPORT}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('failed',1))")
if [ "${FAILED}" -gt 0 ]; then
  echo "=== SOME TESTS FAILED ==="
  exit 1
fi

echo "=== ALL TESTS PASSED ==="
exit 0
