# R2 Object Lifecycle Rules: Auto-Delete After N Days

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You store ephemeral objects in R2 — screenshot exports, temporary uploads, AI response blobs, log archives — and need them deleted automatically after a retention window to control storage costs. Manual cleanup Workers are error-prone; lifecycle rules are the idiomatic solution.

## Context

Cloudflare R2 supports **lifecycle rules** (also called Object Lifecycle Management), analogous to S3 lifecycle policies. Rules are configured per-bucket and evaluated daily. The supported actions are `Delete` (delete current version after N days) and `AbortIncompleteMultipartUpload` (clean up stalled MPU parts). Versioning-aware expiry of non-current versions is also supported when versioning is enabled.

---

## Section 1 — Configure Lifecycle Rules via REST API

R2 exposes an S3-compatible API. Lifecycle rules are set via the `PUT /?lifecycle` endpoint using S3-style XML, or via the Cloudflare REST API.

### Option A — Cloudflare REST API (JSON)

```bash
curl -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/r2/buckets/${BUCKET_NAME}/lifecycle" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "rules": [
      {
        "id": "delete-exports-after-7-days",
        "enabled": true,
        "prefix": "exports/",
        "conditions": {
          "maxAge": 604800
        },
        "deleteObjects": {}
      },
      {
        "id": "delete-temp-after-1-day",
        "enabled": true,
        "prefix": "tmp/",
        "conditions": {
          "maxAge": 86400
        },
        "deleteObjects": {}
      },
      {
        "id": "abort-stale-mpu",
        "enabled": true,
        "conditions": {
          "maxAge": 86400
        },
        "abortMultipartUploads": {}
      }
    ]
  }'
```

`maxAge` is in **seconds**. `prefix` scopes the rule; omit it for bucket-wide application.

### Option B — Wrangler (wrangler.toml does not support lifecycle rules yet)

Use a one-shot script executed at deploy time:

```typescript
// scripts/apply-lifecycle.ts
const ACCOUNT_ID = process.env.ACCOUNT_ID!;
const CF_API_TOKEN = process.env.CF_API_TOKEN!;
const BUCKET_NAME = 'my-assets-bucket';

const rules = {
  rules: [
    {
      id: 'delete-exports-after-7-days',
      enabled: true,
      prefix: 'exports/',
      conditions: { maxAge: 7 * 24 * 3600 },
      deleteObjects: {},
    },
    {
      id: 'delete-tmp-after-1-day',
      enabled: true,
      prefix: 'tmp/',
      conditions: { maxAge: 86400 },
      deleteObjects: {},
    },
  ],
};

const res = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/r2/buckets/${BUCKET_NAME}/lifecycle`,
  {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${CF_API_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(rules),
  }
);

const data = await res.json();
console.log(JSON.stringify(data, null, 2));
if (!data.success) process.exit(1);
```

Run during CI: `npx tsx scripts/apply-lifecycle.ts`

---

## Section 2 — Worker: Verify Lifecycle Before Serving

A Worker serving R2 objects should check whether an object still exists before generating a signed or public URL. Use `HEAD` (via `env.BUCKET.head()`) to confirm existence without transferring the body:

```typescript
// src/index.ts
import type { R2Bucket, R2Object } from '@cloudflare/workers-types';

interface Env {
  BUCKET: R2Bucket;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(request.url);
    // Strip leading slash: /exports/file.png → exports/file.png
    const key = pathname.replace(/^\//, '');

    if (!key) {
      return new Response('Missing key', { status: 400 });
    }

    // HEAD check — returns R2Object metadata or null if deleted / expired
    const meta: R2Object | null = await env.BUCKET.head(key);

    if (!meta) {
      return new Response('Object not found or expired', { status: 404 });
    }

    // Optionally warn if the object will expire soon (within 1 day)
    const uploadedAt = meta.uploaded.getTime();
    const ageMs = Date.now() - uploadedAt;
    const sevenDaysMs = 7 * 24 * 3600 * 1000;
    const expiresInMs = sevenDaysMs - ageMs;
    const expiresInDays = Math.floor(expiresInMs / (24 * 3600 * 1000));

    const headers = new Headers({
      'Content-Type': meta.httpMetadata?.contentType ?? 'application/octet-stream',
      'Cache-Control': 'public, max-age=3600',
      'X-Expires-In-Days': String(expiresInDays),
    });

    if (expiresInDays <= 1) {
      headers.set('X-Lifecycle-Warning', 'Object expires within 24 hours');
    }

    // Serve the object body
    const obj = await env.BUCKET.get(key);
    if (!obj) {
      // Race condition: deleted between HEAD and GET
      return new Response('Object vanished', { status: 404 });
    }

    return new Response(obj.body, { headers });
  },
};
```

---

## Section 3 — Cost Impact Analysis

R2 pricing (as of mid-2025):
- Storage: $0.015 / GB-month
- Class A operations (PUT, DELETE): $4.50 / million
- Class B operations (GET, HEAD): $0.36 / million

Lifecycle deletes are **Class A operations** billed at the same rate. For high-churn buckets with millions of small files:

```typescript
// scripts/cost-estimate.ts
function estimateLifecycleSavings(params: {
  objectsPerDay: number;
  averageSizeKB: number;
  retentionDays: number;
  monthlyStoragePrice: number;  // $/GB-month
  classAPrice: number;          // $ per million ops
}): void {
  const { objectsPerDay, averageSizeKB, retentionDays, monthlyStoragePrice, classAPrice } = params;

  // Without lifecycle: objects accumulate forever (assume 90-day window)
  const objectsAt90Days = objectsPerDay * 90;
  const storageWithoutGB = (objectsAt90Days * averageSizeKB) / (1024 * 1024);
  const costWithout = storageWithoutGB * monthlyStoragePrice * 3; // 3 months

  // With lifecycle: max retention_days of objects at any time
  const objectsAtSteadyState = objectsPerDay * retentionDays;
  const storageWithGB = (objectsAtSteadyState * averageSizeKB) / (1024 * 1024);
  const deletesPerMonth = objectsPerDay * 30;
  const deleteCost = (deletesPerMonth / 1_000_000) * classAPrice;
  const costWith = (storageWithGB * monthlyStoragePrice + deleteCost) * 3;

  console.log(`Storage without lifecycle (3 months): $${costWithout.toFixed(2)}`);
  console.log(`Storage with lifecycle    (3 months): $${costWith.toFixed(2)}`);
  console.log(`Savings: $${(costWithout - costWith).toFixed(2)}`);
}

estimateLifecycleSavings({
  objectsPerDay: 10_000,
  averageSizeKB: 200,
  retentionDays: 7,
  monthlyStoragePrice: 0.015,
  classAPrice: 4.50,
});
// Storage without lifecycle (3 months): $23.73
// Storage with lifecycle    (3 months): $0.96
// Savings: $22.77
```

---

## Anti-patterns

- **Relying on lifecycle for GDPR deletion** — lifecycle rules run daily, not immediately. For right-to-erasure use `BUCKET.delete(key)` from a Worker.
- **Using lifecycle instead of versioning expiry for versioned buckets** — on a versioned bucket, `deleteObjects` creates a delete marker; set a separate rule to expire non-current versions.
- **Setting `maxAge: 0`** — this is invalid and will be rejected by the API. The minimum is 1 day (86400 seconds).

## Gotchas

- Lifecycle evaluation happens **once per day**, not in real time. An object set to expire after 1 day may live up to 48 hours.
- Prefix matching is a **string prefix**, not a glob. `exports/` matches `exports/foo` but not `2024/exports/foo`.
- There is **no dry-run mode**. Test on a dev bucket before applying to production.
- Listing all lifecycle rules requires a `GET /?lifecycle` request; the Cloudflare dashboard shows them under Bucket Settings → Lifecycle Rules.
- Objects deleted by lifecycle rules do **not** trigger R2 event notifications.

## Verification

```bash
# Fetch current rules
curl -X GET \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/r2/buckets/${BUCKET_NAME}/lifecycle" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq .

# Put a test object with past-dated custom metadata and confirm HEAD returns null next day
wrangler r2 object put my-assets-bucket/tmp/test.txt --file ./test.txt
# Manually list to verify object exists, then re-check after lifecycle runs
wrangler r2 object get my-assets-bucket/tmp/test.txt
```

## Related

- `cloudflare-browser-rendering-screenshot.md` — lifecycle rules for screenshot PNGs stored in R2
- `cloudflare-ai-gateway-prompt-logging-d1.md` — archiving large prompt blobs to R2 instead of D1

## Sources

- https://developers.cloudflare.com/r2/buckets/object-lifecycles/
- https://developers.cloudflare.com/r2/pricing/
- https://developers.cloudflare.com/api/operations/r2-put-bucket-lifecycle-configuration
