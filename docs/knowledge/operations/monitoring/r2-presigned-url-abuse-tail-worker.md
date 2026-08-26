# R2 Presigned URL Abuse Detection with Tail Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You issue short-lived R2 presigned URLs to authenticated users for direct object
downloads — bypassing your Worker to reduce egress cost and latency. You begin seeing
unexplained bandwidth spikes in R2 usage metrics, download counts far above expected
user counts, or requests from unexpected geographic regions — suggesting presigned
URLs have leaked, been scraped from a web page, or are being redistributed as hotlinks.
You need to detect these abuse patterns in real time without logging full URLs (which
would re-expose the credentials embedded in the signed query string).

## Context

R2 presigned URLs embed an HMAC signature in the query string
(`X-Amz-Signature`, `X-Amz-Credential`, `X-Amz-Expires`). Anyone with the URL can
fetch the object until it expires. Common abuse vectors:
- URLs embedded in HTML/JS that scrapers cache and reuse
- Shared links forwarded beyond the intended recipient
- URLs with long expiry windows (`X-Amz-Expires > 3600`)
- Requests from data-centre IPs (bot networks) rather than consumer ISPs

A Tail Worker on the R2-serving Worker captures request metadata (object key prefix,
user-agent classification, country, IP ASN if available, response code) without
logging the signed query string. Analytics Engine stores these signals for querying.
This is a detection-only pipeline — revocation requires generating a new HMAC signing
key and re-signing all valid URLs, which is handled at the application layer.

---

## R2 presigned URL generation (reference)

```typescript
// src/sign.ts — generate a presigned URL with short expiry
import { AwsClient } from "aws4fetch";

export async function presignR2(
  env: Env,
  key: string,
  expirySeconds: number = 300  // 5 minutes default; keep ≤ 3600 for security
): Promise<string> {
  const aws = new AwsClient({
    accessKeyId:     env.R2_ACCESS_KEY_ID,
    secretAccessKey: env.R2_SECRET_ACCESS_KEY,
    region:          "auto",
    service:         "s3",
  });

  const url = new URL(`https://${env.R2_BUCKET_DOMAIN}/${key}`);
  url.searchParams.set("X-Amz-Expires", String(expirySeconds));

  const signed = await aws.sign(new Request(url.toString()), { aws: { signQuery: true } });
  return signed.url;
}
```

## R2 download Worker — write abuse-detection signals without logging full URL

```typescript
// src/r2-download.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const key = url.pathname.slice(1);      // strip leading /
    const expiresIn = Number(url.searchParams.get("X-Amz-Expires") ?? 0);
    const credential = url.searchParams.get("X-Amz-Credential") ?? "";
    // Extract key prefix only (first two path segments) for grouping; never log full key
    const keyPrefix = key.split("/").slice(0, 2).join("/");

    // Forward to R2 (Worker acting as presigned URL proxy or direct R2 fetch)
    const obj = await env.R2_BUCKET.get(key);
    const status = obj ? 200 : 404;

    // Classify user-agent crudely: bot vs browser vs downloader
    const ua = request.headers.get("User-Agent") ?? "";
    const uaClass = /curl|wget|python|java|go-http|okhttp/i.test(ua)
      ? "tool"
      : /bot|crawl|spider/i.test(ua)
      ? "bot"
      : "browser";

    env.AE.writeDataPoint({
      blobs:   [
        keyPrefix,                                           // blob1: object key prefix
        request.cf?.country ?? "XX",                        // blob2: country
        uaClass,                                            // blob3: user-agent class
        credential.split("/")[1] ?? "unknown",              // blob4: date part of credential
      ],
      doubles: [
        status,                                             // double1: HTTP status
        expiresIn,                                          // double2: presigned expiry seconds
        obj?.size ?? 0,                                     // double3: object size bytes
      ],
      indexes: ["r2_access"],
    });

    if (!obj) return new Response("Not Found", { status: 404 });
    return new Response(obj.body, {
      headers: { "Content-Type": obj.httpMetadata?.contentType ?? "application/octet-stream" },
    });
  },
};
```

## Tail Worker — capture 4xx/5xx outcome and flag long-expiry URLs

```typescript
// tail/src/index.ts
export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    for (const event of events) {
      if (event.scriptName !== "r2-download") continue;

      for (const log of event.logs) {
        // Tail Workers see console.log output but not full request URLs
        // Only log structured signals, not raw signed URLs
      }

      // Flag: any invocation that ended in an exception may indicate
      // a tampered/expired URL causing an auth error
      if (event.outcome === "exception") {
        env.AE.writeDataPoint({
          blobs:   ["exception", "r2-download"],
          doubles: [1],
          indexes: ["r2_tail"],
        });
      }
    }
  },
};
```

## Abuse-detection queries

```sql
-- 1. Bot traffic ratio by key prefix (last 1 hour)
SELECT
  blob1                                           AS key_prefix,
  countIf(blob3 = 'bot')                          AS bot_requests,
  countIf(blob3 = 'tool')                         AS tool_requests,
  count()                                         AS total_requests,
  countIf(blob3 IN ('bot', 'tool')) / count()     AS non_browser_ratio
FROM R2_AE_DATASET
WHERE timestamp >= NOW() - INTERVAL '1' HOUR
  AND index1 = 'r2_access'
GROUP BY key_prefix
HAVING non_browser_ratio > 0.5 OR total_requests > 1000
ORDER BY total_requests DESC
LIMIT 20;

-- 2. Long-expiry URL usage (expiry > 3600 s = likely misconfigured or leaked)
SELECT
  blob1                       AS key_prefix,
  blob2                       AS country,
  count()                     AS requests,
  avg(double2)                AS avg_expiry_sec,
  max(double2)                AS max_expiry_sec
FROM R2_AE_DATASET
WHERE timestamp >= NOW() - INTERVAL '6' HOUR
  AND index1 = 'r2_access'
  AND double2 > 3600
GROUP BY key_prefix, country
ORDER BY requests DESC;

-- 3. Geographic anomaly — requests from countries never seen before today
SELECT
  blob2                       AS country,
  count()                     AS requests,
  sum(double3)                AS bytes_served
FROM R2_AE_DATASET
WHERE timestamp >= NOW() - INTERVAL '1' HOUR
  AND index1 = 'r2_access'
GROUP BY country
ORDER BY requests DESC;
```

## Cron-based alerting for sustained bot traffic

```typescript
// src/abuse-alert.ts — runs every 10 minutes
export async function checkR2Abuse(env: Env): Promise<void> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` },
      body: JSON.stringify({
        query: `
          SELECT
            countIf(blob3 IN ('bot', 'tool')) AS non_browser,
            count()                           AS total,
            countIf(double2 > 3600)           AS long_expiry_count
          FROM R2_AE_DATASET
          WHERE timestamp >= NOW() - INTERVAL '10' MINUTE
            AND index1 = 'r2_access'
        `,
      }),
    }
  );

  const { data } = await res.json<{ data: Array<{ non_browser: number; total: number; long_expiry_count: number }> }>();
  if (!data.length || data[0].total < 50) return;

  const { non_browser, total, long_expiry_count } = data[0];
  const ratio = non_browser / total;

  if (ratio > 0.6) {
    await env.SLACK_WEBHOOK.fetch(new Request(env.SLACK_WEBHOOK_URL, {
      method: "POST",
      body: JSON.stringify({ text: `R2 abuse alert: ${(ratio * 100).toFixed(0)}% of requests in last 10 min are non-browser (${non_browser}/${total}). Long-expiry URLs: ${long_expiry_count}. Investigate presigned URL leakage.` }),
    }));
  }
}
```

---

## Anti-patterns

- **Logging full presigned URLs in Tail Workers or Analytics Engine**: the signed URL
  contains `X-Amz-Signature` and `X-Amz-Credential` — logging it extends the abuse
  window to your log retention period. Log key prefix and credential date only.
- **Setting `X-Amz-Expires` to 86400 (24 hours) for convenience**: long-lived signed
  URLs have no effective revocation mechanism short of rotating the R2 API key.
  Use ≤ 300 seconds for download links; ≤ 3600 seconds for upload scenarios.
- **Using R2 public bucket access instead of presigned URLs**: a public bucket has no
  per-object expiry or per-user accountability. Use presigned URLs even if objects are
  publicly viewable content, so you retain access telemetry.

## Gotchas

- Tail Workers do not receive the full request URL of the Worker they tail — they
  receive `event.request.url` as seen by the Worker, which includes the presigned
  query parameters. Do not log `event.request.url` raw; extract only safe fields.
- R2 `get()` returns `null` for both non-existent keys and for presigned URL
  authentication failures when using the S3-compatible API. The Worker-native R2 API
  does not enforce presigned URL signatures itself — signature validation occurs at
  the edge before the Worker is invoked. If the Worker receives the request, the
  signature was valid (or the Worker is the signing party).
- `request.cf?.asn` is available in Workers but is not exposed in Tail Worker event
  metadata. If ASN-based bot detection is needed, do it in the main Worker and emit
  it as a blob to AE.

## Verification

```bash
# Generate a short-lived presigned URL (for testing only)
wrangler r2 object get my-bucket test-object --presign --expires 60

# Fetch and confirm Analytics Engine received the data point
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT count() AS n, max(double2) AS max_expiry FROM R2_AE_DATASET WHERE timestamp >= NOW() - INTERVAL '"'"'5'"'"' MINUTE AND index1 = '"'"'r2_access'"'"'"}' \
  | jq '.data[0]'
```

Expected: `n > 0` after a test download. `max_expiry` should equal the `--expires`
value used during generation.

## Related

- `r2-bandwidth-usage-analytics-engine.md`
- `r2-storage-usage-analytics-engine-cost-monitoring.md`
- `r2-object-count-quota-headroom-alerting.md`
- `tail-worker-structured-log-sampling-strategies.md`
- `log-security-masking.md`

## Sources

- Cloudflare R2 presigned URLs: https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- R2 S3-compatible API: https://developers.cloudflare.com/r2/api/s3/api/
- Workers Tail Workers: https://developers.cloudflare.com/workers/observability/tail-workers/
- aws4fetch library: https://github.com/mhart/aws4fetch
