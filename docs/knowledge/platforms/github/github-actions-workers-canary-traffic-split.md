# GitHub Actions Workers Canary Progressive Traffic-Split Rollout

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to release a new Cloudflare Worker version to a small percentage of production traffic first, observe error rate and latency in Cloudflare Analytics, then either promote to 100 % or roll back — all driven from a GitHub Actions workflow without manual Cloudflare dashboard clicks.

## Context

Cloudflare Workers supports **version-based traffic splitting** via the Deployments API (Workers Deployments for gradual rollouts). You upload a new version with `wrangler versions upload`, then create a deployment that assigns a percentage split between the current stable version and the candidate. GitHub Actions orchestrates the upload, the split, a smoke-test window, automated promotion, and rollback on failure. This is distinct from preview environments (separate worker name) — the canary runs under the same production worker name.

## Step 1 — Upload Candidate Version Without Deploying

```yaml
# .github/workflows/canary-deploy.yml
name: Canary rollout
on:
  push:
    branches: [main]

jobs:
  upload:
    runs-on: ubuntu-latest
    outputs:
      version_id: ${{ steps.upload.outputs.version_id }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 22

      - run: npm ci

      - name: Upload candidate version
        id: upload
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          OUTPUT=$(npx wrangler versions upload --json 2>/dev/null)
          VERSION_ID=$(echo "$OUTPUT" | jq -r '.version_id')
          echo "version_id=${VERSION_ID}" >> "$GITHUB_OUTPUT"
          echo "Uploaded version: ${VERSION_ID}"
```

## Step 2 — Retrieve Current Stable Version ID

```typescript
// scripts/get-stable-version.ts
const response = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${process.env.CF_ACCOUNT_ID}/workers/scripts/${process.env.WORKER_NAME}/deployments`,
  { headers: { Authorization: `Bearer ${process.env.CF_API_TOKEN}` } }
);
const data = (await response.json()) as {
  result: { versions: { version_id: string; percentage: number }[] }[];
};
// Current deployment is the first entry
const stable = data.result[0]?.versions.find((v) => v.percentage === 100);
console.log(stable?.version_id ?? "");
```

```yaml
      - name: Get current stable version
        id: stable
        env:
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          WORKER_NAME: ${{ vars.WORKER_NAME }}
        run: |
          STABLE=$(npx tsx scripts/get-stable-version.ts)
          echo "stable_version_id=${STABLE}" >> "$GITHUB_OUTPUT"
```

## Step 3 — Create a 10 % Canary Split Deployment

```yaml
  canary:
    needs: upload
    runs-on: ubuntu-latest
    steps:
      - name: Deploy canary at 10 %
        env:
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          WORKER_NAME: ${{ vars.WORKER_NAME }}
        run: |
          curl -s -X POST \
            "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/${WORKER_NAME}/deployments" \
            -H "Authorization: Bearer ${CF_API_TOKEN}" \
            -H "Content-Type: application/json" \
            --data '{
              "strategy": "percentage",
              "versions": [
                { "version_id": "${{ needs.upload.outputs.version_id }}", "percentage": 10 },
                { "version_id": "${{ needs.stable.outputs.stable_version_id }}", "percentage": 90 }
              ]
            }' | jq '.success'
```

## Step 4 — Observe Error Rate During Canary Window

```bash
# scripts/check-canary-health.sh
# Query Cloudflare GraphQL Analytics API for error rate on the new version
RESPONSE=$(curl -s -X POST "https://api.cloudflare.com/client/v4/graphql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{
    "query": "{ viewer { accounts(filter:{accountTag:\"'"${CF_ACCOUNT_ID}"'\"}) { workersInvocationsAdaptive(limit:1, filter:{scriptName:\"'"${WORKER_NAME}"'\", datetimeHour_geq:\"'"$(date -u -d '10 minutes ago' +%Y-%m-%dT%H:%M:%SZ)"'\"}) { sum { requests errors } } } } }"
  }')

ERRORS=$(echo "$RESPONSE" | jq '.data.viewer.accounts[0].workersInvocationsAdaptive[0].sum.errors // 0')
REQUESTS=$(echo "$RESPONSE" | jq '.data.viewer.accounts[0].workersInvocationsAdaptive[0].sum.requests // 1')
ERROR_RATE=$(echo "scale=4; $ERRORS / $REQUESTS * 100" | bc)

echo "Error rate: ${ERROR_RATE}%"
if (( $(echo "$ERROR_RATE > 1.0" | bc -l) )); then
  echo "ERROR_RATE_HIGH=true" >> "$GITHUB_ENV"
fi
```

## Step 5 — Promote or Roll Back

```yaml
  promote-or-rollback:
    needs: [upload, canary]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Wait canary window (10 min)
        run: sleep 600

      - name: Check canary health
        run: bash scripts/check-canary-health.sh
        env:
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          WORKER_NAME: ${{ vars.WORKER_NAME }}

      - name: Promote to 100 %
        if: env.ERROR_RATE_HIGH != 'true'
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: npx wrangler versions deploy ${{ needs.upload.outputs.version_id }} --percentage 100

      - name: Roll back to stable
        if: env.ERROR_RATE_HIGH == 'true'
        env:
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          WORKER_NAME: ${{ vars.WORKER_NAME }}
        run: |
          curl -s -X POST \
            "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/${WORKER_NAME}/deployments" \
            -H "Authorization: Bearer ${CF_API_TOKEN}" \
            -H "Content-Type: application/json" \
            --data '{
              "strategy": "percentage",
              "versions": [
                { "version_id": "${{ needs.stable.outputs.stable_version_id }}", "percentage": 100 }
              ]
            }'
          echo "::error::Canary rolled back — error rate exceeded threshold"
          exit 1
```

## Anti-patterns

- **Deploying directly with `wrangler deploy` for canary**: `wrangler deploy` always rolls to 100 % immediately. Use `wrangler versions upload` + `wrangler versions deploy --percentage` for traffic splitting.
- **Using preview environments as canary**: Preview workers serve a different hostname; they receive no production traffic and cannot validate real user load.
- **Skipping the stable version lookup**: Hard-coding a previous version ID in the split deployment breaks after every promote cycle.
- **Checking error rate before traffic has stabilised**: A 10 % split needs enough requests to be statistically meaningful; the window should be at least as long as the P95 request duration plus tail latency buffer.

## Gotchas

- `wrangler versions upload --json` output format may include informational lines before the JSON object; use `2>/dev/null` and pipe through `jq` defensively.
- Percentage values in the deployment body must sum to exactly 100; the API returns a 400 otherwise.
- The Workers Deployments API is account-scoped, not zone-scoped; the worker name must match the `name` field in `wrangler.toml`.
- Canary traffic split is **not sticky per user** by default — a single user may hit both versions within one session. Add a `CF-Worker-Version` response header in both versions and log it for correlation.
- `wrangler versions deploy` is behind `--experimental-versions` in Wrangler < 3.40; pin to `wrangler@latest` in CI.

## Verification

```bash
# Confirm active deployment split
curl -s "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/${WORKER_NAME}/deployments" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[0].versions'
```

Expected output:
```json
[
  { "version_id": "abc123", "percentage": 10 },
  { "version_id": "def456", "percentage": 90 }
]
```

## Related

- `github-actions-workers-preview-environments.md`
- `github-actions-cloudflare-deploy-workflow.md`
- `github-actions-workers-multi-region-smoke-test.md`
- `github-actions-retry-failed-workers-deploy.md`
- `github-actions-deployment-gates.md`

## Sources

- https://developers.cloudflare.com/workers/configuration/versions-and-deployments/gradual-deployments/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/deployments/
- https://developers.cloudflare.com/workers/wrangler/commands/#versions
- https://developers.cloudflare.com/analytics/graphql-api/features/filtering/
