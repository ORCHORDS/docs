# Mobile vs Desktop SLO Split: Separate Error Budgets by Device Type

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

example project operates a single availability SLO of 99.5% (3.65 hours downtime/month)
shared across all traffic. When a deploy causes elevated 500 errors on the
mobile client for 20 minutes, the error budget burn rate in aggregate appears
minor because desktop traffic (3× higher volume) dilutes the signal. The
mobile squad is not paged, the SLO dashboard stays green, and mobile users
churn silently.

The root cause: mobile and desktop users have different failure modes,
different tolerances, and different on-call owners. A single shared SLO
hides asymmetric degradation.

The team needs:
- A separate error budget for mobile and desktop traffic.
- Independent burn-rate alerts that page the right squad.
- An authoritative data source (Analytics Engine) that splits errors by
  device type without double-counting.
- A clear policy for what "error" means for each segment.

---

## Context

Service Level Indicators (SLIs) measure what fraction of requests satisfy
a "good request" predicate. For example project:

- **Mobile SLI**: HTTP 2xx response AND wall time < 800 ms, measured on
  requests where `CF-Device-Type: mobile`.
- **Desktop SLI**: HTTP 2xx response AND wall time < 1 200 ms, measured on
  requests where `CF-Device-Type = desktop OR tablet`.
- Bots and health-check probes are excluded from both windows.

Error budget for a given time window = `(1 - SLO) × window_duration`.

| Segment | SLO Target | Monthly Error Budget |
|---------|-----------|---------------------|
| Mobile  | 99.5%     | 3 h 39 min          |
| Desktop | 99.7%     | 2 h 11 min          |

Desktop has a tighter SLO because desktop failures (payment, admin)
carry higher immediate revenue risk. Mobile has more tolerance due to
connection variability.

---

## Section 1: Analytics Engine SLI Data Points

Each Worker invocation writes one data point. The `good_request` double
encodes the SLI pass/fail per segment. The `indexes` field isolates each
device segment for efficient SQL aggregation.

```typescript
// src/lib/slo-metrics.ts
import { resolveDeviceType, type DeviceType } from "./device";

const LATENCY_THRESHOLD: Record<DeviceType, number> = {
  mobile:  800,
  desktop: 1200,
  tablet:  1200,
  bot:     Infinity,   // bots are excluded at query time
  unknown: 1200,
};

export function emitSloDataPoint(
  dataset: AnalyticsEngineDataset,
  request: Request,
  statusCode: number,
  wallTimeMs: number,
): void {
  const deviceType = resolveDeviceType(request);
  if (deviceType === "bot") return;   // exclude bots from SLO windows

  const threshold    = LATENCY_THRESHOLD[deviceType];
  const isGood       = statusCode >= 200 && statusCode < 400 && wallTimeMs <= threshold;
  const isError      = statusCode >= 500;
  const isSlowOk     = statusCode >= 200 && statusCode < 400 && wallTimeMs > threshold;

  dataset.writeDataPoint({
    indexes: [deviceType],
    blobs:   [
      new URL(request.url).pathname,
      String(statusCode),
      request.headers.get("CF-IPCountry") ?? "XX",
    ],
    doubles: [
      isGood   ? 1 : 0,   // double1: good request
      isError  ? 1 : 0,   // double2: server error
      isSlowOk ? 1 : 0,   // double3: slow-but-ok (for latency SLO)
      wallTimeMs,          // double4: wall time
    ],
  });
}
```

```toml
# wrangler.toml
[[analytics_engine_datasets]]
binding = "SLO_METRICS"
dataset = "slo_events_v1"
```

---

## Section 2: SLI and Error Budget SQL Queries

```sql
-- Current error budget consumption: mobile (rolling 30-day)
WITH window AS (
  SELECT
    count()             AS total_requests,
    sum(double1)        AS good_requests,
    count() - sum(double1) AS bad_requests
  FROM  slo_events_v1
  WHERE timestamp > now() - INTERVAL '30' DAY
    AND index1    = 'mobile'
),
budget AS (
  SELECT
    total_requests,
    good_requests,
    bad_requests,
    ROUND(good_requests * 100.0 / total_requests, 4) AS actual_slo_pct,
    -- 99.5% SLO → 0.5% budget
    ROUND(total_requests * 0.005, 0)                 AS budget_requests,
    ROUND(bad_requests * 100.0 / (total_requests * 0.005), 2) AS budget_consumed_pct
  FROM window
)
SELECT * FROM budget;

-- Desktop error budget (tighter: 99.7%)
WITH window AS (
  SELECT
    count()             AS total_requests,
    sum(double1)        AS good_requests,
    count() - sum(double1) AS bad_requests
  FROM  slo_events_v1
  WHERE timestamp > now() - INTERVAL '30' DAY
    AND index1 IN ('desktop', 'tablet')
),
budget AS (
  SELECT
    total_requests,
    good_requests,
    bad_requests,
    ROUND(good_requests * 100.0 / total_requests, 4) AS actual_slo_pct,
    ROUND(total_requests * 0.003, 0)                 AS budget_requests,
    ROUND(bad_requests * 100.0 / (total_requests * 0.003), 2) AS budget_consumed_pct
  FROM window
)
SELECT * FROM budget;

-- 1-hour burn rate (mobile) — how fast is the budget being consumed?
-- Burn rate > 14.4 indicates 100% budget consumed in 2 h (multiwindow alert threshold)
WITH rate AS (
  SELECT
    count()                                              AS total_1h,
    sum(1 - double1)                                     AS bad_1h,
    ROUND((sum(1 - double1) / count()) / 0.005 * 100, 2) AS burn_rate
  FROM  slo_events_v1
  WHERE timestamp > now() - INTERVAL '1' HOUR
    AND index1    = 'mobile'
)
SELECT total_1h, bad_1h, burn_rate FROM rate;
```

---

## Section 3: Burn-Rate Alert Worker (Tail Worker Pattern)

Rather than querying AE on every invocation, a dedicated Tail Worker
aggregates a 1-minute sliding window in a Durable Object counter and
checks burn rate against thresholds.

```typescript
// src/slo-burn-rate-alerter.ts
interface Env {
  BURN_RATE_DO:     DurableObjectNamespace;
  SLACK_MOBILE_URL: string;
  SLACK_DESKTOP_URL: string;
}

interface TraceItem {
  event?: { response?: { status: number }; request?: { url: string; headers: Record<string, string> } };
  wallTime?: number;
}

export default {
  async tail(events: TraceItem[], env: Env, ctx: ExecutionContext): Promise<void> {
    // Batch-forward events to the aggregator DO
    const counts = { mobile_good: 0, mobile_bad: 0, desktop_good: 0, desktop_bad: 0 };

    for (const event of events) {
      const status    = event.event?.response?.status ?? 0;
      const wallMs    = event.wallTime ?? 0;
      const ua        = event.event?.request?.headers?.["CF-Device-Type"] ?? "unknown";
      const isMobile  = ua === "mobile";
      const isDesktop = ua === "desktop" || ua === "tablet";
      const isGoodMobile  = status >= 200 && status < 400 && wallMs <= 800;
      const isGoodDesktop = status >= 200 && status < 400 && wallMs <= 1200;

      if (isMobile) {
        isGoodMobile ? counts.mobile_good++ : counts.mobile_bad++;
      } else if (isDesktop) {
        isGoodDesktop ? counts.desktop_good++ : counts.desktop_bad++;
      }
    }

    const doId   = env.BURN_RATE_DO.idFromName("slo-aggregator");
    const doStub = env.BURN_RATE_DO.get(doId);

    ctx.waitUntil(
      doStub.fetch("https://internal.do/ingest", {
        method: "POST",
        body:   JSON.stringify(counts),
        headers: { "Content-Type": "application/json" },
      }),
    );
  },
};
```

The Durable Object maintains a 1-hour sliding window and fires an alert
when the burn rate exceeds the page threshold:

```typescript
// src/BurnRateAggregator.ts
interface BucketEntry { ts: number; mobile_good: number; mobile_bad: number; desktop_good: number; desktop_bad: number }

export class BurnRateAggregator {
  private window: BucketEntry[] = [];

  constructor(private state: DurableObjectState, private env: { SLACK_MOBILE_URL: string; SLACK_DESKTOP_URL: string }) {}

  async fetch(request: Request): Promise<Response> {
    const body = await request.json<BucketEntry>();
    const now  = Date.now();

    this.window.push({ ...body, ts: now });
    // Trim to 1 hour
    this.window = this.window.filter((e) => now - e.ts < 3_600_000);

    await this.checkBurnRates(now);
    return new Response("ok");
  }

  private async checkBurnRates(now: number): Promise<void> {
    const oneHour = this.window.filter((e) => now - e.ts < 3_600_000);
    const fiveMin = this.window.filter((e) => now - e.ts < 300_000);

    const sum = (arr: BucketEntry[], key: keyof BucketEntry) =>
      arr.reduce((a, b) => a + (b[key] as number), 0);

    // Mobile burn rate (SLO 99.5% → error budget 0.5%)
    const mTotal1h = sum(oneHour, "mobile_good") + sum(oneHour, "mobile_bad");
    if (mTotal1h > 100) {
      const mBurnRate = (sum(oneHour, "mobile_bad") / mTotal1h) / 0.005;
      // Page if burn rate > 14.4 (exhausts 30-day budget in 2 h)
      if (mBurnRate > 14.4) {
        this.state.waitUntil(this.alert(this.env.SLACK_MOBILE_URL, "mobile", mBurnRate, "P1"));
      } else if (mBurnRate > 6) {
        // Warn if burn rate > 6 (exhausts budget in ~5 h)
        this.state.waitUntil(this.alert(this.env.SLACK_MOBILE_URL, "mobile", mBurnRate, "P2"));
      }
    }

    // Desktop burn rate (SLO 99.7% → error budget 0.3%)
    const dTotal1h = sum(oneHour, "desktop_good") + sum(oneHour, "desktop_bad");
    if (dTotal1h > 100) {
      const dBurnRate = (sum(oneHour, "desktop_bad") / dTotal1h) / 0.003;
      if (dBurnRate > 14.4) {
        this.state.waitUntil(this.alert(this.env.SLACK_DESKTOP_URL, "desktop", dBurnRate, "P1"));
      } else if (dBurnRate > 6) {
        this.state.waitUntil(this.alert(this.env.SLACK_DESKTOP_URL, "desktop", dBurnRate, "P2"));
      }
    }
  }

  private async alert(webhookUrl: string, segment: string, burnRate: number, severity: string): Promise<void> {
    await fetch(webhookUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: `*[${severity}] ${segment.toUpperCase()} SLO burn rate: ${burnRate.toFixed(1)}×* — ` +
              `error budget exhaustion projected within ${severity === "P1" ? "2 hours" : "5 hours"}`,
      }),
    });
  }
}
```

---

## Section 4: Error Budget Policy

Document the error budget policy alongside the implementation. This is
the contract between engineering and product.

```markdown
# example project SLO Error Budget Policy

## Mobile segment (99.5% / 30 days)

- Budget remaining > 50%: deploy freely, experiment, run A/B tests.
- Budget remaining 25–50%: restrict risky deploys. Require manual rollback plan.
- Budget remaining 10–25%: freeze non-critical deploys. Mobile squad reviews all changes.
- Budget remaining < 10%: full deploy freeze. Only P1 fixes allowed. Weekly review.
- Budget exhausted: halt all feature work on mobile path. Incident declared.

## Desktop segment (99.7% / 30 days)

- Budget remaining > 50%: deploy freely.
- Budget remaining 25–50%: require postmortem for any degradation event.
- Budget remaining < 25%: deploy freeze. All changes require director approval.
- Budget exhausted: major incident. Executive escalation.

## Exclusions

- Scheduled maintenance windows (communicated 72 h in advance).
- Events caused by Cloudflare infrastructure (documented in Cloudflare status page).
- Bot and health-check traffic (excluded at SLI level via `index1 != 'bot'`).
```

---

## Anti-patterns

- **Shared SLO across device segments** — hides asymmetric degradation.
  A mobile outage diluted by desktop volume will not breach the shared
  budget until it is severe enough to affect aggregate numbers.
- **Using HTTP 4xx in the error count for SLO purposes** — client errors
  (404, 403, 422) are not server failures. Include only 5xx in the "bad
  request" numerator. Latency violations are a separate SLI.
- **Alerting on instantaneous error rate instead of burn rate** — a
  single bad batch of 50 requests fires the alert. Burn rate (error rate
  / error budget fraction) accounts for request volume and gives a
  meaningful signal of budget depletion speed.
- **Resetting the error budget counter at every deploy** — the budget
  resets on a calendar window (monthly), not on deploy boundaries. Teams
  who reset on deploy can hide cumulative degradation across many small
  incidents.
- **Not excluding tablets from the mobile budget** — tablets have desktop-
  like latency tolerances but mobile connectivity. Map `tablet` to the
  desktop SLO threshold to avoid false mobile budget burns from tablet
  network latency.

---

## Gotchas

- Analytics Engine data points have up to 60 seconds of ingestion lag.
  The rolling 1-hour burn rate in the DO is more real-time than the AE
  query because it uses raw event counts from the Tail Worker stream.
- The AE `index1` field stores device type as provided by the Tail Worker
  instrumentation. If the edge Worker has not deployed the `emitSloDataPoint`
  call, the dataset will be empty and the SQL queries will return null.
- WAE does not support `WINDOW` functions (`OVER (ORDER BY ...)`). Use
  sub-selects or CTEs to compute rolling windows.
- The Durable Object burn rate calculation uses in-memory state and is
  lost on cold start. For production use, persist the window buckets to
  DO storage using `this.state.storage.put("window", this.window)` and
  load them in the constructor.
- Burn rate thresholds assume the SLO evaluation window matches the query
  window. A 1-hour burn rate query checked every 5 minutes gives 12
  checks per hour — ensure alert deduplication to avoid 12 pages per
  incident.

---

## Verification

```bash
# Query current mobile budget consumption (last 30 days)
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  --data-urlencode "query=SELECT
    count() AS total,
    sum(double1) AS good,
    count() - sum(double1) AS bad,
    ROUND((count() - sum(double1)) * 100.0 / (count() * 0.005), 2) AS budget_pct
    FROM slo_events_v1
    WHERE timestamp > now() - INTERVAL '30' DAY
      AND index1 = 'mobile'"

# Expected: budget_pct < 100 for a healthy month
# budget_pct = 150 means 50% over budget (incident territory)

# Verify desktop segment is reporting (should have data)
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  --data-urlencode "query=SELECT index1, count() AS n
    FROM slo_events_v1
    WHERE timestamp > now() - INTERVAL '1' HOUR
    GROUP BY index1"
```

---

## Related

- `slo-error-budget-workers-pages.md`
- `slo-error-budgets-burn-rate-alerting.md`
- `error-budget-policy.md`
- `multiwindow-burn-rate-slo-alerts.md`
- `analytics-engine-mobile-desktop-segmentation.md`
- `workers-error-alerting-pagerduty-integration.md`

---

## Sources

- Google SRE Workbook — https://sre.google/workbook/alerting-on-slos/
- Cloudflare Analytics Engine SQL API — https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- SLO burn rate alerting math — https://sre.google/workbook/alerting-on-slos/#6-multiwindow-multi-burn-rate-alerts
- Cloudflare Tail Workers — https://developers.cloudflare.com/workers/observability/tail-workers/
- Cloudflare Durable Objects — https://developers.cloudflare.com/durable-objects/
