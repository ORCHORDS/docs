# KV Write Rate Limit Exceeded Caused Session Token Failures at Scale

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

During a scheduled batch job that refreshed OAuth session tokens for all enterprise customers, roughly 12,000 users were simultaneously logged out and received 401 errors from the example project API. The batch job wrote a new KV token record for each customer session in rapid succession. Workers KV returned `429 Too Many Requests` errors that the job did not handle, causing writes to silently drop. Users whose tokens were not refreshed in time hit the old expiry and were evicted from their sessions.

## Context

example project stores OAuth access tokens in Workers KV under the key pattern `session:{userId}:{provider}` with a TTL matching the token expiry. A nightly Cron Worker called `token-refresh-job` fetches expiring tokens from D1, requests new tokens from upstream OAuth providers, and writes the refreshed tokens back to KV. The job was originally written when the platform had under 500 enterprise users and processed tokens sequentially with a trivial write cadence. As the customer base grew to 12,000 enterprise sessions, the batch job was never revisited for rate-limit safety.

Workers KV enforces a **1,000 writes per second** rate limit per account (across all Workers). The batch job was issuing approximately 4,000 writes per second during its peak window.

## Timeline

- **02:00 UTC** – Cron trigger fires `token-refresh-job` as scheduled.
- **02:00–02:03 UTC** – First 3,000 token writes succeed. KV write rate climbs past 1,000 writes/second.
- **02:03 UTC** – KV begins returning `429 Too Many Requests` for approximately 70% of write attempts.
- **02:03–02:08 UTC** – The job swallows the 429 errors silently (error handling logs to console but does not retry or abort).
- **02:08 UTC** – Token refresh job completes with exit code 0 in the Cron trigger log. 8,400 sessions were not refreshed.
- **03:15 UTC** – First wave of enterprise users in US East timezone start their workday. Sessions expire; 401 errors spike.
- **03:20 UTC** – PagerDuty alert fires: API error rate >5% on authenticated endpoints.
- **03:28 UTC** – On-call engineer identifies 401 spike. Initially suspects D1 migration artifact from previous evening.
- **03:45 UTC** – Worker logs reviewed; `console.error("KV write failed: 429")` entries found in Cron job log from 02:03–02:08.
- **04:00 UTC** – Manual re-run of token refresh job with a 5ms per-write delay; 8,400 sessions refreshed over ~45 seconds.
- **04:10 UTC** – 401 rate returns to baseline. Incident closed.
- **04:30 UTC** – Post-incident retro scheduled.

## Root Cause

The `token-refresh-job` Cron Worker iterated over 12,000 sessions and issued KV writes in a tight async loop using `Promise.all()` over all keys simultaneously. This created a write burst of approximately 4,000 writes per second, 4× the KV account rate limit. The KV client returned `429` errors, but the job treated these as non-fatal console log events rather than retrying or aborting. The job's exit was therefore falsely successful. No alerting existed for KV 429 errors, and no integration test validated that the batch job behaved correctly under rate-limit conditions.

## Fix: Throttled Batch Writes with Retry Back-off

The fix introduces a concurrency-limited write queue with exponential back-off on 429 responses, replacing the unbounded `Promise.all()` pattern.

```typescript
// src/jobs/token-refresh-job.ts

const KV_WRITE_CONCURRENCY = 50;  // max concurrent in-flight KV writes
const KV_WRITE_DELAY_MS = 10;     // minimum ms between each write start
const MAX_RETRIES = 4;

async function refreshTokens(env: Env): Promise<void> {
  // Fetch all sessions expiring within the next 2 hours
  const expiringSessions = await getExpiringSessions(env.example project_DB);
  console.log(`Token refresh job: ${expiringSessions.length} sessions to refresh`);

  const errors: Array<{ userId: string; error: string }> = [];

  await throttledBatch(
    expiringSessions,
    KV_WRITE_CONCURRENCY,
    KV_WRITE_DELAY_MS,
    async (session) => {
      const newToken = await requestNewToken(session, env);
      await writeTokenToKV(env.SESSION_TOKENS, session.userId, newToken);
    },
    (session, err) => {
      errors.push({ userId: session.userId, error: String(err) });
    }
  );

  if (errors.length > 0) {
    console.error(`Token refresh: ${errors.length} failures`, JSON.stringify(errors));
    // Non-zero metric write to AE so dashboards alert
    env.example project_METRICS.writeDataPoint({
      blobs: ["token_refresh_failure"],
      doubles: [errors.length],
      indexes: ["cron_job_errors"],
    });
    // Fail the cron job visibly — do NOT swallow errors
    throw new Error(`Token refresh job failed for ${errors.length} sessions`);
  }

  console.log("Token refresh job: all sessions refreshed successfully");
}

async function writeTokenToKV(
  kv: KVNamespace,
  userId: string,
  token: OAuthToken
): Promise<void> {
  const key = `session:${userId}:${token.provider}`;
  const value = JSON.stringify(token);
  const ttlSeconds = Math.floor((token.expiresAt - Date.now()) / 1000);

  let attempt = 0;
  while (attempt < MAX_RETRIES) {
    try {
      await kv.put(key, value, { expirationTtl: Math.max(ttlSeconds, 60) });
      return;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      if (message.includes("429") || message.includes("rate limit")) {
        const backoffMs = 200 * Math.pow(2, attempt); // 200ms, 400ms, 800ms, 1600ms
        attempt++;
        if (attempt >= MAX_RETRIES) throw err;
        await sleep(backoffMs);
      } else {
        throw err; // non-rate-limit errors are not retried
      }
    }
  }
}

async function throttledBatch<T>(
  items: T[],
  concurrency: number,
  delayMs: number,
  work: (item: T) => Promise<void>,
  onError: (item: T, err: unknown) => void
): Promise<void> {
  let index = 0;
  const workers = Array.from({ length: concurrency }, async () => {
    while (index < items.length) {
      const item = items[index++];
      await sleep(delayMs);
      try {
        await work(item);
      } catch (err) {
        onError(item, err);
      }
    }
  });
  await Promise.all(workers);
}

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}
```

## Prevention Checklist

- [ ] Never use `Promise.all()` for bulk KV writes without a concurrency cap; use a throttled batch utility.
- [ ] Treat KV `429` responses as retriable errors with exponential back-off, not silent no-ops.
- [ ] Ensure Cron Workers throw (or return a failure sentinel) when a meaningful fraction of batch items fail, so the platform logs a failed execution rather than a false success.
- [ ] Add a KV write rate metric (writes per second sampled from the batch job) to the observability dashboard with an alert threshold at 80% of the 1,000/s limit.
- [ ] Load-test batch jobs against projected future customer counts, not current counts, before shipping.

## Monitoring Gaps Identified

- KV `429` errors logged to `console.error` inside the Cron Worker were not forwarded to Logpush or Sentry, so the batch job failure was invisible until user 401 errors surfaced nearly an hour later.
- The Cron trigger log showed a successful exit even though 70% of writes failed, because the job swallowed the error and exited normally.

## Anti-patterns

- Using `Promise.all()` over thousands of write operations against a rate-limited API without any throttling.
- Treating infrastructure rate limit responses (`429`) as acceptable silent failures in a batch job that has correctness requirements.
- Relying on user-facing error rates as the detection mechanism for background job failures — the feedback loop is too slow and the blast radius too large.

## Gotchas

- Workers KV write rate limit is **1,000 writes per second per account**, shared across all Workers and Cron triggers running simultaneously. A single batch job can consume the entire account budget.
- KV `put()` does not currently throw a typed `KVRateLimitError`; the 429 is surfaced as a generic `Error` with a message that includes "429" or "rate limit" — pattern-match on the message string until a typed error class is available.
- KV reads are cached at the edge and have much higher throughput than writes; asymmetric write/read rate limits are easy to miss if you only test read-heavy paths.

## Verification

```bash
# Run the token refresh job in dry-run mode and measure KV write throughput
curl -X POST "https://example project-admin.workers.dev/internal/cron/token-refresh?dryRun=true" \
  -H "Authorization: Bearer $example project_ADMIN_TOKEN" | jq '.writesPerSecond'

# Tail Worker logs during a test run to confirm 429 handling
npx wrangler tail token-refresh-job --env production --format pretty 2>&1 | grep -i "429\|rate limit\|retry"

# Query AE for cron_job_errors data points to confirm alerting path works
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  --data '{"query":"SELECT sum(double1) AS failures FROM example project_metrics WHERE blob1 = '\''token_refresh_failure'\'' AND timestamp > NOW() - INTERVAL '\''1'\'' HOUR"}' \
  | jq '.data'
```

## Related

- `lessons/kv-cold-start-mobile-latency-spike-postmortem.md`
- `lessons/kv-read-costs-capacity-planning-retrospective.md`
- `lessons/queue-backlog-death-spirals.md`
- `lessons/rate-limit-before-you-need-it.md`

## Sources

- https://developers.cloudflare.com/kv/platform/limits/
- https://developers.cloudflare.com/workers/runtime-apis/kv/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
