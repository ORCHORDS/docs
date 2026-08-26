# performance-baseline-tracking

**Issue:** Establishing and tracking performance baselines across deployments to detect regressions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Without baselines, teams cannot distinguish a performance regression from normal variance. Baselines captured per release allow objective comparison and gate enforcement.

## Pattern / Solution
Capture baseline after each release:
```bash
#!/bin/bash
# post-deploy-baseline.sh
VERSION=$1
ENDPOINT="https://staging.myapp.example.com"

# Run k6 and capture JSON output
k6 run --out json=results.json load-test.js

# Extract key metrics
P50=$(jq '.metrics.http_req_duration.values["p(50)"]' results.json)
P95=$(jq '.metrics.http_req_duration.values["p(95)"]' results.json)
P99=$(jq '.metrics.http_req_duration.values["p(99)"]' results.json)
RPS=$(jq '.metrics.http_reqs.values.rate' results.json)
ERR=$(jq '.metrics.errors.values.rate' results.json)

# Store in performance DB
psql $PERF_DB -c "
  INSERT INTO perf_baselines (version, captured_at, p50_ms, p95_ms, p99_ms, rps, error_rate)
  VALUES ('$VERSION', NOW(), $P50, $P95, $P99, $RPS, $ERR);
"

echo "Baseline stored for $VERSION: p50=${P50}ms p95=${P95}ms"
```

Regression check in CI:
```bash
# Compare current to last N baselines
BASELINE=$(psql $PERF_DB -t -c "
  SELECT p95_ms FROM perf_baselines
  ORDER BY captured_at DESC LIMIT 1;
" | tr -d ' ')

CURRENT_P95=$(jq '.metrics.http_req_duration.values["p(95)"]' results.json)
THRESHOLD=$(echo "$BASELINE * 1.15" | bc)  # 15% regression threshold

python3 -c "
import sys
if float('$CURRENT_P95') > float('$THRESHOLD'):
    print(f'FAIL: p95 {$CURRENT_P95}ms > threshold {$THRESHOLD}ms (baseline {$BASELINE}ms)')
    sys.exit(1)
print(f'PASS: p95 {$CURRENT_P95}ms within 15% of baseline {$BASELINE}ms')
"
```

Grafana annotation on deploy:
```bash
curl -X POST "$GRAFANA_URL/api/annotations" \
  -H "Authorization: Bearer $GRAFANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"text\": \"Deploy: myapp $VERSION\",
    \"tags\": [\"deploy\", \"myapp\"],
    \"time\": $(date +%s000)
  }"
```

## Gotchas
- Baselines vary with load; always run under the same synthetic load profile for comparability
- Infrastructure changes (instance type, region) invalidate old baselines — annotate and reset
- Latency percentiles are sensitive to tail latency outliers; p99 swings more than p95 between runs — use p95 as the primary gate
- Compare absolute values, not just ratios — a 15% regression from 10ms to 11.5ms is irrelevant; from 400ms to 460ms is critical

## Related
- `load-testing-before-deploy.md`
- `deployment-metrics-tracking.md`
- `slo-alerting-thresholds.md`
