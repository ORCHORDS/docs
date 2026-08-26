# gdpr-data-export-worker-r2-signed-url

**Issue:** GDPR data export ZIP exceeds Worker memory limits;
  presigned R2 URL expires before mobile user downloads it;
  D1 queries time out for accounts with >50 k content rows
**Date:** 2026-08-22
**Author:** example.com
**Status:** open

## Symptom

1. Requesting a data export for a large account throws `Error:
   Worker exceeded memory limit (128 MB)` in the export-generation
   Worker during ZIP assembly.
2. Mobile users receive the presigned R2 download URL by email;
   ~18% click it after the 15-minute expiry and see an R2 403.
3. D1 `SELECT * FROM posts WHERE user_id = ?` on accounts with
   50 000+ posts causes a Worker CPU timeout after 30 seconds.

## Context

Under GDPR Article 15 (right of access) and Article 20 (data
portability), example project must provide a machine-readable export of all
personal data within 30 days of request. The export is a ZIP
archive with JSON files for each data category. Because example project is
anonymous, exports include pseudonymous IDs rather than real names,
but posts, DMs, reactions, and trust-score history are still
personal data under GDPR Recital 26.

## Architecture

Do not build the ZIP inside a single Worker invocation. Use a
Cloudflare Queue consumer (15-minute execution budget via retry
batches) to page through D1, write JSON parts to R2 with streaming
multipart upload, and send the presigned URL when done:

```
POST /api/gdpr/export
    │  Worker creates export_request row in D1
    │  Enqueues job to Cloudflare Queue
    ▼
CF Queue consumer Worker
    │  1. Pages through D1 in batches of 1 000 rows (keyset)
    │  2. Streams each batch to R2 multipart upload part
    │  3. On completion: marks D1 row complete,
    │     emails presigned URL to verified contact
    ▼
R2: export_<user_id>_<epoch>.zip
    ▼
User downloads via 48-hour presigned URL
```

## D1 Query Optimisation for Large Exports

Never `SELECT *` across large tables without a cursor. Use keyset
pagination on the primary key to avoid full-table scans per page:

```ts
let cursor: string | null = null;
const batchSize = 1_000;

do {
  const stmt = cursor
    ? env.DB.prepare(
        `SELECT id, content, created_at
           FROM posts
          WHERE user_id = ?1
            AND id > ?2
          ORDER BY id
          LIMIT ?3`
      ).bind(userId, cursor, batchSize)
    : env.DB.prepare(
        `SELECT id, content, created_at
           FROM posts
          WHERE user_id = ?1
          ORDER BY id
          LIMIT ?2`
      ).bind(userId, batchSize);

  const rows = await stmt.all();
  await writeToR2MultipartPart(rows.results, env);
  cursor = rows.results.at(-1)?.id ?? null;
} while (cursor !== null);
```

Required covering index — add in a migration before enabling the
export endpoint:

```sql
CREATE INDEX idx_posts_user_id_id ON posts(user_id, id);
```

Without this, D1 performs a full-table scan on every page. With it,
each page is a fast index range scan.

## R2 Presigned URL and Expiry Handling

Workers R2 bindings do not natively issue presigned URLs. Use
`aws4fetch` with the R2 S3-compatible endpoint:

```ts
import { AwsClient } from 'aws4fetch';

const r2 = new AwsClient({
  accessKeyId:     env.R2_ACCESS_KEY_ID,
  secretAccessKey: env.R2_SECRET_ACCESS_KEY,
  service:         's3',
  region:          'auto',
});

const signed = await r2.sign(
  new Request(
    `https://${env.R2_ACCOUNT_ID}.r2.cloudflarestorage.com`
      + `/exports/${key}`,
    { method: 'GET' }
  ),
  {
    aws:       { signQuery: true },
    // 48-hour expiry — covers email delivery delay + mobile tap lag
    expiresIn: 172_800,
  }
);

const presignedUrl = signed.url;
```

```
┌────────────┬──────────────────────────────────────────────────┐
│ Expiry     │ Trade-off                                        │
├────────────┼──────────────────────────────────────────────────┤
│ 15 minutes │ Minimal exposure; breaks mobile email→click→     │
│            │ download on slow connections or deferred opens   │
├────────────┼──────────────────────────────────────────────────┤
│ 48 hours   │ Safe for mobile; covers email delivery delays;   │
│            │ acceptable for pseudonymous export data          │
├────────────┼──────────────────────────────────────────────────┤
│ 7 days     │ GDPR DPA guidance: "reasonable"; fine for low-   │
│            │ sensitivity pseudonymous exports per WP29 note   │
└────────────┴──────────────────────────────────────────────────┘
```

example project policy: 48-hour expiry. Store the expiry epoch in D1
(`export_requests.url_expires_at`). If a user clicks an expired
link, regenerate the presigned URL from the existing R2 object
(do not regenerate the export itself) and re-send the notification.

```sql
CREATE TABLE export_requests (
  id             TEXT PRIMARY KEY,
  user_id        TEXT NOT NULL,
  status         TEXT NOT NULL DEFAULT 'queued',
                   -- 'queued'|'building'|'complete'|'failed'
  r2_key         TEXT,
  url_expires_at INTEGER,
  requested_at   INTEGER NOT NULL DEFAULT (unixepoch()),
  completed_at   INTEGER
);
```

## Mobile Download Compatibility

```
┌─────────────────────┬────────────────────┬──────────────────────┐
│ Platform            │ Default behaviour  │ Fix                  │
├─────────────────────┼────────────────────┼──────────────────────┤
│ iOS Safari          │ Opens ZIP in       │ Serve via Worker     │
│ (share → Files)     │ browser as listing │ with Content-        │
│                     │                    │ Disposition:         │
│                     │                    │ attachment           │
├─────────────────────┼────────────────────┼──────────────────────┤
│ Android Chrome      │ Downloads to       │ No fix needed        │
│                     │ Downloads folder   │                      │
├─────────────────────┼────────────────────┼──────────────────────┤
│ In-app WebView      │ May not trigger    │ Open URL in system   │
│ (iOS/Android)       │ download; hangs    │ browser via          │
│                     │                    │ window.open()        │
└─────────────────────┴────────────────────┴──────────────────────┘
```

R2 presigned URLs do not support response-override headers (unlike
S3's `response-content-disposition`). Proxy through a thin Worker
that sets the correct download headers:

```ts
// workers/export-download.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const key = await validateExportKey(req, env); // checks D1
    if (!key) return new Response('Not found', { status: 404 });

    const obj = await env.EXPORTS_BUCKET.get(key);
    if (!obj) return new Response('Expired', { status: 410 });

    return new Response(obj.body, {
      headers: {
        'Content-Type': 'application/zip',
        'Content-Disposition':
          `attachment; filename="example project-export.zip"`,
        'Cache-Control': 'private, no-store',
      },
    });
  },
};
```

## Anti-patterns

- **Building the full ZIP in a Worker's in-memory buffer.** A
  50 k-post export can exceed 128 MB easily. Use streaming
  multipart R2 upload or a Queue-based pipeline.
- **Deleting the R2 object after the URL expires.** The object is
  needed for URL regeneration. Schedule deletion 30 days after
  `completed_at`, or after the user confirms receipt via a
  read-receipt webhook.
- **Including raw IP logs for other users in the export.** IP
  addresses of users who viewed content are not the requesting
  data subject's data. Include only the subject's own action logs.

## Gotchas

- `aws4fetch` presigned URLs for R2 must use the account-specific
  endpoint (`<account_id>.r2.cloudflarestorage.com`), not a
  generic S3 endpoint.
- D1 `batch()` accepts up to 100 statements per call. Do not batch
  1 000 INSERT statements in one call when writing export metadata
  rows.
- Cloudflare Queue consumers retry failed message batches up to 3
  times. Make the export pipeline idempotent by using
  `export_request.id` as the R2 multipart upload key prefix.

## Verification

```
# Trigger export, wait for queue consumer, check D1 status
curl -X POST https://example project.app/api/gdpr/export \
  -H 'Authorization: Bearer <token>'
# → { "request_id": "exp_abc", "status": "queued" }

# Poll status endpoint
curl https://example project.app/api/gdpr/export/exp_abc
# → { "status": "complete", "download_url": "https://..." }

# Confirm R2 object exists and is a valid ZIP
wrangler r2 object get exports/<key> --pipe | file -
# → Zip archive data, at least v2.0 to extract
```

## Related

- `documentation/categories/issues/d1-column-affinity-gotcha.md`
- `documentation/categories/issues/d1-integer-overflow-javascript.md`
- `documentation/categories/issues/kv-metadata-size-limit.md`
- `documentation/categories/issues/gdpr-article-22-automated-decisions-2026.md`

## Source URLs

- https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/d1/
- https://gdpr-info.eu/art-15-gdpr/
- https://gdpr-info.eu/art-20-gdpr/
