# Worker Versioning: Gradual Rollout via Versions API

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Deploying a new Worker bundle to 100% of traffic immediately exposes all users
to any latent bug in the new code. Error rate spikes are detected only after
the impact is large. Manual rollback requires a full re-deploy cycle
(30–90 seconds), during which errors continue.

## Context

Cloudflare's Worker Versions API (GA as of late 2025) enables percentage-based
traffic routing between two uploaded Worker versions without changing the
Worker's public URL. example project (example.com) uses this to roll out backend changes
progressively: 5% → 20% → 50% → 100%, with automatic rollback if the error
rate on the new version exceeds a threshold.

Prerequisites:
- Account must enable "Workers Gradual Deployments" in the dashboard or via API
- `wrangler` >= 3.60.0
- A Cloudflare analytics token with `Account Analytics:Read` scope for
  error-rate polling

---

## Worker Versions API Overview

```
POST /accounts/:account_id/workers/scripts/:script_name/versions
  → uploads a new version, returns version_id

POST /accounts/:account_id/workers/scripts/:script_name/deployments
  → creates or updates a deployment with traffic percentages

GET  /accounts/:account_id/workers/scripts/:script_name/deployments/latest
  → returns current routing state

DELETE /accounts/:account_id/workers/scripts/:script_name/deployments/:deployment_id
  → not used for rollback; update deployment percentages instead
```

### Version Upload

```bash
# Upload new bundle without deploying it to any traffic
VERSION_ID=$(curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/workers/scripts/example project-api/versions" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -F "worker=@dist/worker.js;type=application/javascript+module" \
  -F 'metadata={"main_module":"worker.js","compatibility_date":"2026-08-01"}' \
  | jq -r '.result.id')

echo "Uploaded version: $VERSION_ID"
```

### Deployment Object Schema

```json
{
  "versions": [
    { "version_id": "<STABLE_VERSION_ID>", "percentage": 80 },
    { "version_id": "<CANARY_VERSION_ID>",  "percentage": 20 }
  ]
}
```

Percentages must sum to exactly 100. Traffic assignment is per-request,
not per-session — use KV session pinning if stickiness is required.

---

## Gradual Rollout Script

```bash
#!/usr/bin/env bash
# scripts/gradual-rollout.sh
set -euo pipefail

ACCOUNT_ID=$1
SCRIPT=$2
NEW_VERSION=$3
STABLE_VERSION=$4
ERROR_THRESHOLD=${5:-2}   # percent; rollback if exceeded
CHECK_INTERVAL=${6:-120}  # seconds between checks

BASE="https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/workers/scripts/$SCRIPT"
AUTH=(-H "Authorization: Bearer $CF_API_TOKEN")

set_split() {
  local new_pct=$1
  local stable_pct=$((100 - new_pct))
  curl -s -X POST "$BASE/deployments" "${AUTH[@]}" \
    -H "Content-Type: application/json" \
    -d "{\"versions\":[
          {\"version_id\":\"$STABLE_VERSION\",\"percentage\":$stable_pct},
          {\"version_id\":\"$NEW_VERSION\",\"percentage\":$new_pct}
        ]}" | jq -r '.success'
}

get_error_rate() {
  # Query Workers Analytics API for error rate on new version over last 5 min
  local result
  result=$(curl -s "${AUTH[@]}" \
    "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/workers/analytics/queries" \
    -H "Content-Type: application/json" \
    -d "{
      \"query\": \"SELECT sum(requests) as total, sum(errors) as errors FROM WorkerAnalytics WHERE scriptName='$SCRIPT' AND versionId='$NEW_VERSION' AND datetime > NOW() - INTERVAL '5' MINUTE\"
    }")
  local total errors
  total=$(echo "$result" | jq -r '.result.data[0].total // 1')
  errors=$(echo "$result" | jq -r '.result.data[0].errors // 0')
  echo "scale=2; $errors * 100 / $total" | bc
}

rollback() {
  echo "ROLLBACK: error rate exceeded threshold"
  set_split 0   # 100% stable
  exit 1
}

for PCT in 5 20 50 100; do
  echo "Routing $PCT% to new version $NEW_VERSION"
  set_split "$PCT"
  sleep "$CHECK_INTERVAL"

  if [[ "$PCT" -lt 100 ]]; then
    ERR=$(get_error_rate)
    echo "Error rate on new version: ${ERR}%"
    if (( $(echo "$ERR > $ERROR_THRESHOLD" | bc -l) )); then
      rollback
    fi
  fi
done

echo "Rollout complete. 100% on $NEW_VERSION"
```

---

## Traffic Percentage Routing Table

| Stage | New Version % | Stable Version % | Soak time | Auto-rollback threshold |
|-------|--------------|-----------------|-----------|------------------------|
| 1     | 5            | 95              | 2 min     | 2% error rate          |
| 2     | 20           | 80              | 5 min     | 2% error rate          |
| 3     | 50           | 50              | 10 min    | 1.5% error rate        |
| 4     | 100          | 0               | —         | Alert only (P95 latency)|

---

## Monitoring Error Rate During Rollout

Use Cloudflare Workers Analytics to compare error rates between versions in
real time.

```typescript
// monitoring/error-rate.ts — run as a Deno script in CI
const ACCOUNT = Deno.env.get("CF_ACCOUNT_ID")!;
const TOKEN   = Deno.env.get("CF_API_TOKEN")!;
const SCRIPT  = Deno.env.get("WORKER_SCRIPT")!;
const VERSION = Deno.env.get("NEW_VERSION_ID")!;

async function fetchErrorRate(): Promise<number> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}/workers/analytics/queries`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        query: `
          SELECT
            SUM(requests) AS total,
            SUM(errors)   AS errors
          FROM WorkerAnalytics
          WHERE scriptName = '${SCRIPT}'
            AND versionId  = '${VERSION}'
            AND datetime   > NOW() - INTERVAL '5' MINUTE
        `,
      }),
    }
  );
  const { result } = await res.json();
  const row = result.data[0];
  return row.total === 0 ? 0 : (row.errors / row.total) * 100;
}

// Poll every 30 s during rollout
const intervalId = setInterval(async () => {
  const rate = await fetchErrorRate();
  console.log(`Error rate: ${rate.toFixed(2)}%`);
  if (rate > 2) {
    console.error("Threshold exceeded — trigger rollback");
    Deno.exit(1);
  }
}, 30_000);
```

---

## Auto-Rollback on Threshold Breach

```bash
# rollback.sh — call from CI on failure signal
#!/usr/bin/env bash
set -euo pipefail
ACCOUNT_ID=$1
SCRIPT=$2
STABLE_VERSION=$3

echo "Auto-rollback: routing 100% to $STABLE_VERSION"

curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/workers/scripts/$SCRIPT/deployments" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"versions\":[{\"version_id\":\"$STABLE_VERSION\",\"percentage\":100}]}" \
  | jq '{success, result}'

# Record in KV for audit trail
wrangler kv:key put --namespace-id="$NS_ID" \
  "deploy:last_rollback_ts"   "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
wrangler kv:key put --namespace-id="$NS_ID" \
  "deploy:last_rollback_reason" "error_rate_threshold"
```

### GitHub Actions Integration

```yaml
- name: Gradual rollout
  id: rollout
  run: bash scripts/gradual-rollout.sh "$ACCOUNT_ID" "example project-api" "$NEW_VER" "$STABLE_VER"
  env:
    CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

- name: Auto-rollback on failure
  if: failure() && steps.rollout.outcome == 'failure'
  run: bash scripts/rollback.sh "$ACCOUNT_ID" "example project-api" "$STABLE_VER"
  env:
    CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

---

## Anti-patterns

- **Jumping straight from 0% to 100%** — defeats the purpose; use at least
  one intermediate percentage with a soak window.
- **Using version IDs from `wrangler deploy` standard output** — standard
  `wrangler deploy` does not use the Versions API; you must upload via the
  Versions endpoint to get a `version_id`.
- **Measuring error rate globally instead of per-version** — a pre-existing
  stable error rate will mask new version regressions. Filter by `versionId`.
- **Setting the threshold too high (> 5%)** — at 5 req/s × 5% = 0.25 rps
  erroring, the rollback never triggers within the soak window. Use 1–2%.
- **Not storing the stable `version_id` before starting the rollout** — if
  you lose it, rollback requires a fresh re-deploy.

---

## Gotchas

- Worker Versions are immutable once uploaded. If a version has a bug in its
  uploaded metadata (e.g., wrong `compatibility_date`), upload a corrected
  version — you cannot patch an existing one.
- Traffic percentages apply at the edge; a single user may hit both versions
  across requests unless you implement KV session pinning.
- The Workers Analytics API has a ~2-minute data lag. Your soak window must
  be longer than the lag; 5 minutes minimum per stage is recommended.
- `wrangler tail` does not filter by `version_id` yet (as of Wrangler 3.60).
  Use the API or dashboard to see per-version error counts.

---

## Verification

```bash
# Check current deployment percentages
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/workers/scripts/example project-api/deployments/latest" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  | jq '.result.versions'

# List uploaded versions
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/workers/scripts/example project-api/versions" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  | jq '.result[] | {id, created_on}'
```

---

## Related

- `canary-workers-gradual-traffic-split.md`
- `progressive-canary-deployment-rollback.md`
- `blue-green-deploy-cloudflare-workers.md`
- `rollback-strategies-workers-pages.md`
- `deployment-metrics-tracking.md`

## Sources

- Cloudflare Workers Versions API — https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
- Workers Analytics Engine — https://developers.cloudflare.com/analytics/analytics-engine/
- Cloudflare blog: Gradual Deployments — https://blog.cloudflare.com/gradual-deployments/
