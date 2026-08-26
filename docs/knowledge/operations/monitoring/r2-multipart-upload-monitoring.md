# R2 Multipart Upload Lifecycle Monitoring

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Large file uploads to R2 use the multipart upload API: `createMultipartUpload`,
`uploadPart`, then `completeMultipartUpload` or `abortMultipartUpload`. If clients crash
or time out mid-upload the parts remain stored in R2 and accumulate storage costs without
producing a usable object. Without visibility into in-progress, completed, and abandoned
multipart uploads you cannot detect cost leakage or diagnose upload reliability problems.

## Context

R2 charges for storage of incomplete multipart upload parts just like completed objects.
A single large in-progress upload can hold gigabytes of parts indefinitely if the
initiating client never calls `abort`. Cloudflare does not auto-expire incomplete uploads
by default. Monitoring should track: multipart initiation rate, part upload throughput,
completion vs. abort outcomes, and the count of uploads that exceed a maximum age
threshold (indicating abandonment).

Because R2 bindings run inside Workers, all monitoring events can be written directly
to Analytics Engine in the same request context, with no external agent required.

## Tracking Multipart Upload Initiation and Completion

```typescript
// r2-multipart-monitor.ts
export interface MultipartEvent {
  uploadId: string;
  key: string;
  bucket: string;
  action: "initiated" | "part_uploaded" | "completed" | "aborted";
  partNumber?: number;
  partSizeBytes?: number;
  totalPartsExpected?: number;
  durationMs?: number;
}

export function recordMultipartEvent(env: Env, event: MultipartEvent): void {
  env.ANALYTICS.writeDataPoint({
    blobs: [
      event.bucket,
      event.action,
      event.uploadId,
      event.key,
    ],
    doubles: [
      event.partNumber ?? 0,
      event.partSizeBytes ?? 0,
      event.totalPartsExpected ?? 0,
      event.durationMs ?? 0,
    ],
    indexes: [event.bucket],
  });
}
```

## Instrumented R2 Multipart Upload Wrapper

```typescript
// r2-upload.ts
export async function monitoredMultipartUpload(
  env: Env,
  bucket: R2Bucket,
  key: string,
  parts: ReadableStream[],
  contentType: string
): Promise<void> {
  const start = Date.now();
  const upload = await bucket.createMultipartUpload(key, {
    httpMetadata: { contentType },
  });

  recordMultipartEvent(env, {
    uploadId: upload.uploadId,
    key,
    bucket: "primary",
    action: "initiated",
    totalPartsExpected: parts.length,
  });

  const completedParts: R2UploadedPart[] = [];
  let partNumber = 1;

  for (const stream of parts) {
    const partStart = Date.now();
    const partData = await new Response(stream).arrayBuffer();
    const uploaded = await upload.uploadPart(partNumber, partData);

    recordMultipartEvent(env, {
      uploadId: upload.uploadId,
      key,
      bucket: "primary",
      action: "part_uploaded",
      partNumber,
      partSizeBytes: partData.byteLength,
      durationMs: Date.now() - partStart,
    });

    completedParts.push(uploaded);
    partNumber++;
  }

  await upload.complete(completedParts);

  recordMultipartEvent(env, {
    uploadId: upload.uploadId,
    key,
    bucket: "primary",
    action: "completed",
    totalPartsExpected: parts.length,
    durationMs: Date.now() - start,
  });
}
```

## Detecting Abandoned Uploads via Scheduled Worker

```typescript
// abandoned-upload-cleaner.ts
// Scans for multipart initiations with no completion or abort within the TTL window.
// Runs as a Cron Trigger: "0 */6 * * *"

const ABANDONED_TTL_HOURS = 24;

export async function detectAbandonedUploads(env: Env): Promise<void> {
  const query = `
    SELECT
      blob3 AS upload_id,
      blob4 AS key,
      MIN(timestamp) AS initiated_at,
      groupArray(blob2) AS actions
    FROM r2_multipart_events
    WHERE timestamp > NOW() - INTERVAL '${ABANDONED_TTL_HOURS + 6}' HOUR
    GROUP BY upload_id, key
    HAVING NOT has(actions, 'completed') AND NOT has(actions, 'aborted')
      AND MIN(timestamp) < NOW() - INTERVAL '${ABANDONED_TTL_HOURS}' HOUR
  `;

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query }),
    }
  );

  const { data } = await resp.json<{
    data: Array<{ upload_id: string; key: string; initiated_at: string }>;
  }>();

  for (const abandoned of data) {
    // Persist to D1 for runbook-driven manual review before aborting
    await env.DB.prepare(
      `INSERT OR IGNORE INTO abandoned_uploads (upload_id, key, initiated_at, detected_at)
       VALUES (?, ?, ?, ?)`
    )
      .bind(abandoned.upload_id, abandoned.key, abandoned.initiated_at, new Date().toISOString())
      .run();
  }

  if (data.length > 0) {
    await fetch(env.SLACK_WEBHOOK_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: `R2: ${data.length} abandoned multipart upload(s) detected older than ${ABANDONED_TTL_HOURS}h. Review \`abandoned_uploads\` table before aborting.`,
      }),
    });
  }
}
```

## Measuring Upload Completion Rate per Bucket

```typescript
// completion-rate-query.ts
export async function fetchMultipartCompletionRate(
  env: Env,
  windowHours = 24
): Promise<{ completionRate: number; abortRate: number; pendingCount: number }> {
  const query = `
    SELECT
      blob2 AS action,
      COUNT() AS n
    FROM r2_multipart_events
    WHERE timestamp > NOW() - INTERVAL '${windowHours}' HOUR
      AND blob2 IN ('initiated', 'completed', 'aborted')
    GROUP BY action
  `;

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query }),
    }
  );

  const { data } = await resp.json<{ data: Array<{ action: string; n: number }> }>();
  const byAction = Object.fromEntries(data.map((r) => [r.action, r.n]));

  const initiated = byAction["initiated"] ?? 0;
  const completed = byAction["completed"] ?? 0;
  const aborted = byAction["aborted"] ?? 0;

  return {
    completionRate: initiated > 0 ? completed / initiated : 1,
    abortRate: initiated > 0 ? aborted / initiated : 0,
    pendingCount: initiated - completed - aborted,
  };
}
```

## Anti-patterns

- Ignoring incomplete multipart uploads entirely — parts count toward your R2 storage
  bill from the moment they are written, regardless of whether the upload completes.
- Aborting abandoned uploads automatically without a review step — a slow client may
  still be uploading; abort only uploads older than a conservative TTL (24h+).
- Storing upload state exclusively in Workers memory or KV without a durable record —
  if the Worker crashes mid-upload, state is lost and cleanup becomes impossible.
- Conflating `abort` with failure — a clean cancellation by the client is expected
  behaviour; only report aborts as failures if they follow a part-upload error.

## Gotchas

- `bucket.createMultipartUpload` does not reserve quota; parts accumulate charges
  individually. A 10 GB upload abandoned after 5 GB costs for all 5 GB stored.
- R2 multipart upload IDs are bucket-scoped, not globally unique — include bucket name
  when storing IDs in D1 to avoid collisions across buckets.
- Cloudflare R2 does not emit native lifecycle-expiry events for incomplete uploads
  (as of 2026-08); you must run your own cron-based detection.
- Analytics Engine `groupArray` and `has` functions follow ClickHouse semantics;
  confirm syntax against the Analytics Engine SQL dialect documentation.

## Verification

```bash
# Count events by action in the last 24 hours
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"query":"SELECT blob2 AS action, COUNT() AS n FROM r2_multipart_events WHERE timestamp > NOW() - INTERVAL 24 HOUR GROUP BY action ORDER BY n DESC"}' \
  | jq '.data'

# Check D1 for abandoned uploads pending review
wrangler d1 execute my-db --command \
  "SELECT upload_id, key, initiated_at, detected_at FROM abandoned_uploads ORDER BY detected_at DESC LIMIT 20"
```

## Related

- `r2-bandwidth-usage-analytics-engine.md`
- `r2-storage-usage-analytics-engine-cost-monitoring.md`
- `cloudflare-logpush-r2-partitioned-athena.md`
- `workers-request-size-anomaly-detection-d1.md`
- `batch-job-monitoring.md`

## Sources

- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/#multipart-upload-methods
- https://developers.cloudflare.com/r2/buckets/object-lifecycles/
- https://developers.cloudflare.com/analytics/analytics-engine/
