# Bot Management Score Distribution Monitoring with Analytics Engine

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Bot Management is active but you have no visibility into the score distribution of your traffic. A sudden influx of low-score (bot) traffic, a score-distribution shift after a firmware campaign, or a mis-tuned firewall rule silently blocking legitimate users with mid-range scores all go undetected until business metrics degrade. You need a continuous view of how bot scores are distributed across endpoints and time.

## Context

Cloudflare Bot Management assigns every HTTP request a score from **1** (almost certainly a bot) to **99** (almost certainly human). The score is available in the request `cf` object inside a Worker or Tail Worker as `cf.botManagement.score`. Tail Workers can capture this for every request without adding latency to the main Worker, bucket scores into ranges, and write data points to Analytics Engine for trending and alerting. The resulting dataset enables p5/p50/p95 score queries, per-URL bot profiles, and sudden-shift detection.

Bot score ranges by convention:
- 1–29: Likely automated
- 30–59: Uncertain / headless browser
- 60–99: Likely human

## Tail Worker: Capturing Bot Score per Request

```typescript
// tail-worker.ts — deploy as a Tail Worker bound to your main Worker
interface Env {
  AE: AnalyticsEngineDataset;
}

interface BotManagement {
  score: number;
  verifiedBot: boolean;
  staticResource: boolean;
  detectionIds?: Record<string, string>;
}

export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    for (const event of events) {
      const cf = event.cf as (CloudflareProperties & { botManagement?: BotManagement }) | undefined;
      const score = cf?.botManagement?.score ?? -1;
      if (score === -1) continue; // Bot Management not enabled on this zone/route

      const url = new URL(event.scriptName ?? "unknown://worker");
      const pathname = url.pathname.slice(0, 64); // cap cardinality

      // Bucket into coarse ranges for dimensional queries
      const bucket =
        score <= 29 ? "bot" : score <= 59 ? "uncertain" : "human";

      env.AE.writeDataPoint({
        blobs: [
          bucket,
          event.outcome ?? "unknown",  // success | exception | exceededCpu | etc.
          pathname,
        ],
        doubles: [score, 1],
        indexes: [bucket],
      });
    }
  },
} satisfies ExportedHandler<Env>;
```

## Analytics Engine SQL: Score Distribution and Percentiles

```sql
-- Score bucket distribution over last 24 h
SELECT
  blob1 AS score_bucket,
  sum(double2) AS request_count,
  round(sum(double2) * 100.0 / sum(sum(double2)) OVER (), 2) AS pct_of_traffic
FROM bot_management_scores
WHERE timestamp > NOW() - INTERVAL '24' HOUR
GROUP BY 1
ORDER BY request_count DESC;

-- Hourly average bot score (lower = more bots)
SELECT
  toStartOfHour(timestamp) AS hour,
  round(avg(double1), 1) AS avg_score,
  countIf(double1 <= 29) AS bot_requests,
  countIf(double1 >= 60) AS human_requests
FROM bot_management_scores
WHERE timestamp > NOW() - INTERVAL '7' DAY
GROUP BY 1
ORDER BY 1;

-- Top paths by bot-traffic share
SELECT
  blob3 AS path,
  sum(double2) AS total,
  countIf(blob1 = 'bot') AS bot_count,
  round(countIf(blob1 = 'bot') * 100.0 / sum(double2), 1) AS bot_pct
FROM bot_management_scores
WHERE timestamp > NOW() - INTERVAL '1' HOUR
GROUP BY 1
HAVING total > 100
ORDER BY bot_pct DESC
LIMIT 20;
```

## Detecting Sudden Bot Score Shifts

```typescript
// Scheduled Worker: compare current-hour avg score vs previous-hour
export default {
  async scheduled(_event: ScheduledEvent, env: Env & { CF_API_TOKEN: string; CF_ACCOUNT_ID: string; ALERT_URL: string }) {
    const sql = `
      SELECT
        toStartOfHour(timestamp) AS hour,
        avg(double1) AS avg_score
      FROM bot_management_scores
      WHERE timestamp > NOW() - INTERVAL '2' HOUR
      GROUP BY 1
      ORDER BY 1
    `;

    const res = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${env.CF_API_TOKEN}`, "Content-Type": "text/plain" },
        body: sql,
      }
    );

    const { data } = (await res.json()) as { data: { hour: string; avg_score: number }[] };
    if (data.length < 2) return;

    const [prev, curr] = data.slice(-2);
    const drop = prev.avg_score - curr.avg_score;

    if (drop > 15) {
      // Average score dropped >15 points in one hour — likely bot surge
      await fetch(env.ALERT_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: `[WARNING] Bot score avg dropped ${drop.toFixed(1)} pts (${prev.avg_score.toFixed(1)} → ${curr.avg_score.toFixed(1)}). Possible bot surge.`,
        }),
      });
    }
  },
};
```

## Correlating Bot Score with Error Rate

```sql
-- Does bot traffic cause higher error rates?
SELECT
  blob1 AS score_bucket,
  blob2 AS outcome,
  sum(double2) AS requests
FROM bot_management_scores
WHERE timestamp > NOW() - INTERVAL '1' HOUR
GROUP BY 1, 2
ORDER BY 1, requests DESC;
```

## Anti-patterns

- **Writing raw score as a blob dimension**: Raw integer scores (1–99) create 99 distinct cardinality values per path. Always bucket into 3–5 named ranges before writing to blobs.
- **Alerting on instantaneous bot count**: A single high-bot minute might be a Cloudflare health probe. Alert on rolling 15-minute average or use burn-rate logic.
- **Ignoring `cf.botManagement.verifiedBot`**: Verified bots (Googlebot, etc.) score low but are legitimate. Filter or separately track `verifiedBot: true` to avoid false positives.
- **Tail Worker in same script as main Worker**: Tail Workers must be a separate Worker deployment; they cannot tail themselves.

## Gotchas

- `cf.botManagement` is only populated when Bot Management (paid add-on) is enabled on the zone — it is `undefined` on zones with only Bot Fight Mode.
- The `score` field is absent (`undefined`) for requests that bypass Bot Management (e.g., IP allowlisted or from a trusted ASN). Always guard with `?? -1` and skip those.
- Analytics Engine blob values count toward cardinality limits; keep pathname capped and avoid logging full query strings.
- Bot scores are computed per-request in real time — there is no historical score enrichment via API.

## Verification

1. Enable Bot Management on your zone and deploy the Tail Worker.
2. Send a synthetic request via `curl -A "curl/7.0"` (typically scores low) and a browser request (scores high).
3. Query Analytics Engine within 60 seconds:
   ```bash
   curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
     -H "Authorization: Bearer $CF_API_TOKEN" \
     --data-raw "SELECT blob1, double1 FROM bot_management_scores ORDER BY timestamp DESC LIMIT 10"
   ```
4. Confirm two rows appear with different buckets.

## Related

- `tail-worker-structured-error-classification-d1.md`
- `firewall-event-spike-anomaly-detection.md`
- `workers-tail-real-time-log-streaming.md`
- `analytics-engine-cardinality-management-multi-dimension.md`
- `r2-presigned-url-abuse-tail-worker.md`

## Sources

- Cloudflare Bot Management: https://developers.cloudflare.com/bots/
- `cf.botManagement` object: https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- Tail Workers: https://developers.cloudflare.com/workers/observability/tail-workers/
- Analytics Engine SQL API: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
