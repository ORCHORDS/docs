# Workers Placement Score Monitoring Post-Deploy

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
After enabling Cloudflare Smart Placement or deploying a Worker to a new region configuration, teams have no automated signal confirming that placement is working as intended—requests may silently default to sub-optimal regions, increasing p99 latency and external backend round-trip times without triggering any alert.

## Context
Cloudflare Smart Placement (`placement: { mode: "smart" }`) dynamically re-locates Worker execution closer to upstream services rather than the end user. After a deploy, the placement engine needs time (typically 5–30 minutes) to gather telemetry and converge. A post-deploy monitoring job should poll the `cf.colo` header, compare actual execution regions against expected ones, and write placement telemetry to Analytics Engine for trending. This provides a feedback loop that makes placement regressions visible in dashboards and alerts.

## Capturing Placement Metadata at Runtime

```typescript
// src/index.ts — instrument every request with placement context
export interface Env {
  ANALYTICS: AnalyticsEngineDataset;
  EXPECTED_COLO: string; // e.g. "IAD,LHR,NRT" — comma-separated expected PoPs
}

function parseExpectedColos(raw: string): Set<string> {
  return new Set(raw.split(",").map((s) => s.trim().toUpperCase()));
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const startMs = Date.now();
    const cf = request.cf ?? {};

    // Actual execution colo reported by the runtime
    const actualColo = (cf.colo as string | undefined) ?? "UNKNOWN";
    const clientCountry = (cf.country as string | undefined) ?? "XX";
    const tlsVersion = (cf.tlsVersion as string | undefined) ?? "none";

    const expectedColos = parseExpectedColos(env.EXPECTED_COLO);
    const isExpectedPlacement = expectedColos.has(actualColo);

    // Emit to Analytics Engine
    ctx.waitUntil(
      (async () => {
        env.ANALYTICS.writeDataPoint({
          blobs: [actualColo, clientCountry, tlsVersion],
          doubles: [
            Date.now() - startMs,        // processing_ms
            isExpectedPlacement ? 1 : 0, // placement_hit (1=good, 0=miss)
          ],
          indexes: [actualColo],
        });
      })()
    );

    const result = await handleRequest(request, env);

    // Expose placement info in response headers for synthetic monitors
    return new Response(result.body, {
      status: result.status,
      headers: {
        ...Object.fromEntries(result.headers),
        "X-Worker-Colo": actualColo,
        "X-Placement-Hit": isExpectedPlacement ? "1" : "0",
      },
    });
  },
};

async function handleRequest(
  request: Request,
  _env: Env
): Promise<{ body: string; status: number; headers: Record<string, string> }> {
  // Application logic placeholder
  return { body: JSON.stringify({ ok: true }), status: 200, headers: {} };
}
```

## Wrangler Configuration

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[placement]
mode = "smart"

[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset  = "worker_placement_telemetry"

# Expected PoPs after Smart Placement convergence (comma-separated IATA codes)
[vars]
EXPECTED_COLO = "IAD,LHR,SIN,NRT"
```

## Post-Deploy Convergence Monitor Script

```typescript
// scripts/monitor-placement.ts
// Run after deploy; poll for placement convergence and alert on misses.

const WORKER_URL = process.env.WORKER_URL!;
const EXPECTED_COLOS = (process.env.EXPECTED_COLO ?? "IAD,LHR").split(",");
const PROBE_COUNT = parseInt(process.env.PROBE_COUNT ?? "20", 10);
const MISS_THRESHOLD = parseFloat(process.env.MISS_THRESHOLD ?? "0.3"); // 30% miss = alert
const PROBE_INTERVAL_MS = parseInt(process.env.PROBE_INTERVAL_MS ?? "5000", 10);

interface PlacementResult {
  colo: string;
  hit: boolean;
  latency_ms: number;
}

async function probe(): Promise<PlacementResult> {
  const start = performance.now();
  const res = await fetch(WORKER_URL, { method: "GET" });
  const latency_ms = Math.round(performance.now() - start);

  const colo = res.headers.get("X-Worker-Colo") ?? "UNKNOWN";
  const hit = res.headers.get("X-Placement-Hit") === "1";

  await res.body?.cancel();
  return { colo, hit, latency_ms };
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

const results: PlacementResult[] = [];
const coloCounts: Record<string, number> = {};

console.log(`Probing ${WORKER_URL} ${PROBE_COUNT} times...`);

for (let i = 0; i < PROBE_COUNT; i++) {
  const result = await probe();
  results.push(result);
  coloCounts[result.colo] = (coloCounts[result.colo] ?? 0) + 1;

  const status = result.hit ? "✓" : "✗";
  console.log(
    `[${i + 1}/${PROBE_COUNT}] ${status} colo=${result.colo} latency=${result.latency_ms}ms`
  );

  if (i < PROBE_COUNT - 1) await sleep(PROBE_INTERVAL_MS);
}

const hits = results.filter((r) => r.hit).length;
const hitRate = hits / PROBE_COUNT;
const missRate = 1 - hitRate;
const avgLatency = results.reduce((s, r) => s + r.latency_ms, 0) / PROBE_COUNT;
const p99Latency = [...results].sort((a, b) => b.latency_ms - a.latency_ms)[
  Math.floor(PROBE_COUNT * 0.01)
]!.latency_ms;

console.log("\n=== Placement Report ===");
console.log(`Expected colos : ${EXPECTED_COLOS.join(", ")}`);
console.log(`Hit rate       : ${(hitRate * 100).toFixed(1)}%`);
console.log(`Miss rate      : ${(missRate * 100).toFixed(1)}%`);
console.log(`Avg latency    : ${avgLatency.toFixed(0)} ms`);
console.log(`p99 latency    : ${p99Latency} ms`);
console.log("Colo distribution:");
for (const [colo, count] of Object.entries(coloCounts).sort((a, b) => b[1] - a[1])) {
  const pct = ((count / PROBE_COUNT) * 100).toFixed(1);
  const bar = "█".repeat(Math.round(Number(pct) / 5));
  console.log(`  ${colo.padEnd(8)} ${bar} ${pct}%`);
}

if (missRate > MISS_THRESHOLD) {
  console.error(
    `\nPLACEMENT ALERT: miss rate ${(missRate * 100).toFixed(1)}% exceeds threshold ${(MISS_THRESHOLD * 100).toFixed(1)}%`
  );
  process.exit(1);
}

console.log("\nPlacement check PASSED.");
```

## Analytics Engine Dashboard Query

```sql
-- Cloudflare Analytics Engine SQL API query for placement trend
-- POST https://api.cloudflare.com/client/v4/accounts/{account_id}/analytics_engine/sql

SELECT
  blob1                                   AS colo,
  toStartOfInterval(timestamp, INTERVAL '5' MINUTE) AS bucket,
  count()                                 AS requests,
  avg(double1)                            AS avg_processing_ms,
  sumIf(double2, double2 = 1) / count()  AS placement_hit_rate
FROM worker_placement_telemetry
WHERE
  timestamp >= now() - INTERVAL '2' HOUR
GROUP BY
  colo, bucket
ORDER BY
  bucket DESC, requests DESC
```

## GitHub Actions Post-Deploy Monitor Job

```yaml
# .github/workflows/deploy.yml (post-deploy placement monitor step)
  post-deploy-placement-check:
    name: Placement convergence check
    needs: deploy
    runs-on: ubuntu-latest
    # Give Smart Placement time to converge before probing
    # (add a wait step if your pipeline runs immediately after deploy)

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
      - run: npm ci

      - name: Wait for placement convergence
        run: sleep 120

      - name: Run placement monitor
        run: npx tsx scripts/monitor-placement.ts
        env:
          WORKER_URL: ${{ vars.WORKER_URL }}
          EXPECTED_COLO: ${{ vars.EXPECTED_PLACEMENT_COLOS }}
          PROBE_COUNT: "30"
          MISS_THRESHOLD: "0.25"
          PROBE_INTERVAL_MS: "3000"
        timeout-minutes: 10

      - name: Alert on placement regression
        if: failure()
        uses: slackapi/slack-github-action@v2
        with:
          webhook: ${{ secrets.SLACK_DEPLOY_WEBHOOK }}
          webhook-type: incoming-webhook
          payload: |
            {
              "text": ":warning: Smart Placement miss rate exceeded threshold after deploy of `${{ github.sha }}`.\nWorker: ${{ vars.WORKER_URL }}\nRun: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
            }
```

## Anti-patterns
- Probing placement immediately after `wrangler deploy` completes — Smart Placement requires time to gather request samples before the optimizer converges; early probes will report false misses.
- Using client IP for expected-colo assertions in a CI environment — CI runners typically exit from a single data center; this biases probe results toward that region's PoP.
- Setting `EXPECTED_COLO` to a single PoP — Smart Placement distributes across multiple PoPs; a strict single-colo assertion produces false alarms.
- Disabling placement monitoring after the first passing run — placement can drift when upstream service topology changes or Cloudflare PoP capacity shifts.
- Conflating execution colo with client-edge colo — the Anycast edge receiving the TLS connection and the PoP where Worker JS executes may differ with Smart Placement.

## Gotchas
- `request.cf.colo` returns the PoP where the Worker *executes*, not where the user's packet first arrived at the Cloudflare network.
- Analytics Engine datasets are eventually consistent; SQL queries may lag actual traffic by 30–60 seconds.
- Smart Placement is only effective for Workers that make subrequest calls to external or internal services; a pure-compute Worker with no fetch calls will not benefit and placement may remain at edge.
- The `placement: { mode: "smart" }` field requires Wrangler 3.x and a Workers Paid plan; silently ignored on free tier.
- Probe-based miss rates from a single geographic origin (CI runner) are not a substitute for real-user telemetry; use Analytics Engine data for production signal.

## Verification
1. Deploy with `placement.mode = "smart"` and wait 5 minutes.
2. Run `npx tsx scripts/monitor-placement.ts` manually and confirm the colo distribution table shows multiple PoPs.
3. Temporarily set `EXPECTED_COLO` to a colo that will never serve the probe (e.g., `AAA`) and confirm the script exits non-zero.
4. Query Analytics Engine with the SQL above and confirm `placement_hit_rate` is above 0.7 after 30 minutes of traffic.
5. Confirm `X-Worker-Colo` header is present in curl output: `curl -I https://your-worker.example.com | grep X-Worker-Colo`.

## Related
- `cloudflare-smart-placement-deploy-optimization.md`
- `deploy-cost-attribution-per-service-d1-billing.md`
- `deployment-health-gates-automated-rollback.md`
- `wrangler-tail-logs-deployment-verification.md`
- `post-deploy-monitoring-checklist.md`

## Sources
- https://developers.cloudflare.com/workers/configuration/smart-placement/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
