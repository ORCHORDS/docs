# anonymous-content-reporting-worker-pipeline

**Issue:** Coordinated mass-flagging auto-removes legitimate posts;
  mobile attachment uploads silently time out; CSAM detection hook
  is not wired into the report ingestion Worker
**Date:** 2026-08-22
**Author:** example.com
**Status:** open

## Symptom

1. A single post receives 400+ reports within 2 minutes, triggering
   auto-removal before human review. Investigation shows a single
   VPN-hopping actor using automated tooling.
2. Mobile users submitting a screenshot attachment see the "Report
   submitted" confirmation, but the attachment never arrives —
   multipart upload silently times out on slow connections.
3. A report with `reason = 'csam'` reaches the human moderation
   queue without triggering the CSAM hash check integration.

## Context

example project content reporting is fully anonymous — reporters are not
linked to accounts. The report Worker receives
`{ content_id, reason, optional_attachment }` via POST with no
auth header. Rate limiting and deduplication must rely on IP and
browser fingerprint only. The pipeline must handle mobile users
on 3G connections and coordinated abuse from sophisticated actors.

## Rate Limiting by IP and Fingerprint

Use `CF-Connecting-IP` and a hashed combination of `User-Agent` +
`Accept-Language` + `CF-IPCountry` as a fingerprint. Store counts
in KV with a 60-second sliding window:

```ts
async function isRateLimited(
  req: Request,
  env: Env
): Promise<boolean> {
  const ip  = req.headers.get('CF-Connecting-IP') ?? 'unknown';
  const fp  = await fingerprintRequest(req); // sha256(UA+AL+country)
  const key = `rl:report:${ip}:${fp}`;

  const raw   = await env.KV.get(key);
  const count = raw ? parseInt(raw, 10) : 0;

  if (count >= 5) return true;  // 5 reports per 60 s per fingerprint

  await env.KV.put(key, String(count + 1), { expirationTtl: 60 });
  return false;
}
```

This does not stop a determined actor cycling IPs, but combined
with the D1 aggregation threshold below it provides adequate
friction for casual abuse.

## D1 Report Aggregation Schema

```sql
CREATE TABLE content_reports (
  id               TEXT PRIMARY KEY,
  content_id       TEXT NOT NULL,
  reason           TEXT NOT NULL, -- 'spam'|'hate'|'csam'|'nudity'
  reporter_fp      TEXT NOT NULL, -- hashed fingerprint
  reported_at      INTEGER NOT NULL DEFAULT (unixepoch()),
  attachment_r2_key TEXT,         -- R2 object key, nullable
  escalated        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE report_aggregates (
  content_id    TEXT PRIMARY KEY,
  report_count  INTEGER NOT NULL DEFAULT 0,
  last_reported INTEGER,
  auto_removed  INTEGER NOT NULL DEFAULT 0,
  csam_flagged  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_reports_content
    ON content_reports(content_id, reporter_fp);
CREATE INDEX idx_reports_reason
    ON content_reports(reason, reported_at);
```

Increment `report_aggregates` inside a D1 batch to avoid double-
counting from concurrent submissions:

```ts
await env.DB.batch([
  env.DB.prepare(
    `INSERT INTO content_reports
       (id, content_id, reason, reporter_fp)
     VALUES (?1, ?2, ?3, ?4)`
  ).bind(id, contentId, reason, fp),

  env.DB.prepare(
    `INSERT INTO report_aggregates
       (content_id, report_count, last_reported)
     VALUES (?1, 1, unixepoch())
     ON CONFLICT(content_id) DO UPDATE
       SET report_count  = report_count + 1,
           last_reported = unixepoch()`
  ).bind(contentId),
]);
```

## Escalation Thresholds

```
┌────────────────────────┬────────────────┬──────────────────────┐
│ Condition              │ Threshold      │ Action               │
├────────────────────────┼────────────────┼──────────────────────┤
│ Unique reporter FPs    │ ≥ 3 unique FPs │ Queue for human      │
│                        │ within 10 min  │ review               │
├────────────────────────┼────────────────┼──────────────────────┤
│ reason = 'csam'        │ 1 report       │ Immediate CSAM hash  │
│                        │                │ check + auto-hide    │
├────────────────────────┼────────────────┼──────────────────────┤
│ Total report count     │ ≥ 20 within    │ Auto-remove +        │
│ (any sources)          │ 1 hour         │ notify ops           │
├────────────────────────┼────────────────┼──────────────────────┤
│ Coordinated FP cluster │ >15 reports    │ Shadow-ban FP        │
│ detected               │ from same FP   │ cluster; discard     │
│                        │ cluster        │ further reports      │
└────────────────────────┴────────────────┴──────────────────────┘
```

Count distinct `reporter_fp` per `content_id` in D1 on each insert.
Keep a covering index on `(content_id, reporter_fp)` and evaluate
only at insert time, not on every read.

## Mobile vs Desktop Reporting UX

```
┌─────────────────────┬──────────────────────┬───────────────────┐
│ Aspect              │ Desktop              │ Mobile            │
├─────────────────────┼──────────────────────┼───────────────────┤
│ Attachment upload   │ Multipart form, up   │ Presigned R2 PUT  │
│                     │ to 10 MB via Worker  │ URL; client posts │
│                     │                      │ file direct to R2 │
├─────────────────────┼──────────────────────┼───────────────────┤
│ Report confirmation │ Inline toast         │ Full-screen modal │
│                     │                      │ (iOS sheet)       │
├─────────────────────┼──────────────────────┼───────────────────┤
│ Background submit   │ Not needed           │ Beacon API for    │
│ on tab close        │                      │ non-attachment    │
│                     │                      │ reports           │
├─────────────────────┼──────────────────────┼───────────────────┤
│ Retry on failure    │ Browser retry on     │ Explicit retry UI;│
│                     │ refresh              │ offline queue in  │
│                     │                      │ IndexedDB         │
└─────────────────────┴──────────────────────┴───────────────────┘
```

Mobile attachment fix: instead of streaming through the Worker,
issue a presigned R2 PUT URL (64-second TTL) from the report
endpoint. The client uploads the file directly. The Worker stores
only the `attachment_r2_key` in D1 after an upload-complete
webhook fires.

## CSAM Detection Integration

On any report with `reason = 'csam'`, call the CSAM hash check
*before* acknowledging the report to the client. example project uses a
stubbed interface `lib/csam.ts` until vendor onboarding completes
(see `877-csam-vendor-integration.md`):

```ts
if (reason === 'csam') {
  const imageKey = report?.attachment_r2_key;
  const match    = imageKey
    ? await env.CSAM.checkHash(imageKey)
    : 'no-image';

  await env.DB.prepare(
    `UPDATE report_aggregates
        SET csam_flagged = 1
      WHERE content_id = ?1`
  ).bind(contentId).run();

  if (match === 'match') {
    // Auto-remove, preserve evidence, begin NCMEC pipeline
    await triggerNcmecPipeline(contentId, imageKey, env);
  }
}
```

## Anti-patterns

- **Trusting `X-Forwarded-For` for rate limiting.** On Cloudflare,
  use `CF-Connecting-IP` only — it cannot be spoofed by the client.
- **Streaming large attachments through the Worker.** Workers have
  a 128 MB body limit and a 30-second CPU time limit. Route uploads
  directly to R2 via presigned URLs.
- **Auto-removing content on `report_count` alone.** Without
  unique-source deduplication, a single actor can mass-flag any
  post into removal.
- **Accepting `reason = 'csam'` without immediate content hiding.**
  CSAM-flagged content must be hidden before human review begins.

## Gotchas

- KV writes have eventual consistency. In a burst, two concurrent
  report Workers may both read `count=0` and both write `count=1`.
  Accept this — the rate limiter is a friction layer, not a hard
  cap. Hard caps are enforced at the D1 aggregate level.
- D1 `INSERT ... ON CONFLICT DO UPDATE` counts as two operations
  against the D1 row-write limit. Monitor D1 write metrics when
  report volume spikes.
- The Beacon API (`navigator.sendBeacon`) sets `Content-Type` to
  `text/plain`. The Worker must parse the body as text/JSON even
  when `Content-Type: application/json` is not sent.

## Verification

```
# Rate limit: 6th report from same IP should return 429
for i in $(seq 1 6); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST https://example project.app/api/report \
    -H 'Content-Type: application/json' \
    -d '{"content_id":"c1","reason":"spam"}'
done
# → 200 200 200 200 200 429

# CSAM flag: reason=csam must set csam_flagged=1 in D1
wrangler d1 execute example project-db --command \
  "SELECT csam_flagged FROM report_aggregates
    WHERE content_id='c1'"
# → 1
```

## Related

- `documentation/docs/policies/issues/877-csam-vendor-integration.md`
- `documentation/docs/policies/issues/platform-trust-score-cloudflare-signals.md`
- `documentation/docs/policies/issues/kv-metadata-size-limit.md`
- `documentation/docs/policies/issues/content-moderation-appeals-workflow.md`

## Source URLs

- https://developers.cloudflare.com/workers/runtime-apis/kv/
- https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- https://developers.cloudflare.com/d1/
- https://developer.mozilla.org/en-US/docs/Web/API/Navigator/sendBeacon
- https://www.ncmec.org/cybertipline/
