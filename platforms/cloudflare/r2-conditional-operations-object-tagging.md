# R2: Conditional Operations and Object Tagging

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You need to implement optimistic concurrency on R2 objects — for example, updating a shared
config file only if no one else has changed it since your last read. You also need to tag
objects with custom metadata that query-level operations (lifecycle rules, batch jobs) can
filter on without fetching the full object body. Both requirements go beyond the basic
`put/get/delete` API.

## Context

R2 exposes two complementary capabilities for fine-grained object control:

**Conditional headers** — R2's `get`, `put`, and `delete` operations accept an `onlyIf` option
mirroring HTTP conditional request semantics:
- `etagMatches` / `etagDoesNotMatch` — compare against the stored ETag (MD5 of object body).
- `uploadedBefore` / `uploadedAfter` — compare against the object's `uploaded` timestamp.

A failed condition returns `null` from `get` and throws a `PreconditionFailed` error from
`put`; your code must handle both branches.

**Object tagging** — R2 objects can carry up to 10 user-defined key-value string tags set at
upload time (`customMetadata` in the Workers API is separate; tags are the `tags` field). Tags
persist through `copy` operations and are returned in `head` responses without fetching the
body. They are also the filter criterion for R2 lifecycle rules and event notification filters.

Object tags are distinct from `customMetadata`: tags are limited to 128-byte keys and 256-byte
values, and the R2 S3-compatible API surfaces them as `x-amz-tagging` headers. `customMetadata`
supports richer values but is not available in lifecycle rule filters.

## Conditional Read (Optimistic Lock — Read Side)

```typescript
// src/conditional-read.ts
interface Env { BUCKET: R2Bucket; }

interface ReadResult {
  body: string | null;
  etag: string | null;
  notModified: boolean;
}

export async function readIfChanged(
  bucket: R2Bucket,
  key: string,
  knownEtag: string | null,
): Promise<ReadResult> {
  const object = await bucket.get(key, {
    onlyIf: knownEtag
      ? { etagDoesNotMatch: knownEtag }  // only fetch if ETag changed
      : undefined,
  });

  if (object === null) {
    // Condition not met — ETag unchanged, cached copy is still current
    return { body: null, etag: knownEtag, notModified: true };
  }

  const body = await object.text();
  return { body, etag: object.etag, notModified: false };
}
```

## Conditional Write (Optimistic Concurrency Control)

```typescript
// src/conditional-write.ts

/** Atomically updates an object only if the ETag still matches (no-one changed it). */
export async function updateIfUnchanged(
  bucket: R2Bucket,
  key: string,
  newContent: string,
  expectedEtag: string,
  contentType = "application/json",
): Promise<{ success: boolean; currentEtag: string | null }> {
  try {
    const result = await bucket.put(key, newContent, {
      httpMetadata: { contentType },
      onlyIf: { etagMatches: expectedEtag },
    });

    return { success: true, currentEtag: result.etag };
  } catch (err) {
    if (err instanceof Error && err.message.includes("PreconditionFailed")) {
      // Another writer modified the object between our read and write
      const head = await bucket.head(key);
      return { success: false, currentEtag: head?.etag ?? null };
    }
    throw err;
  }
}

/** Full optimistic-lock cycle: read → modify → write with retry. */
export async function compareAndSwap(
  bucket: R2Bucket,
  key: string,
  transform: (current: string | null) => string,
  maxRetries = 3,
): Promise<boolean> {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    const obj = await bucket.get(key);
    const current = obj ? await obj.text() : null;
    const currentEtag = obj?.etag ?? null;
    const next = transform(current);

    if (currentEtag === null) {
      // Object does not exist — create it
      await bucket.put(key, next);
      return true;
    }

    const { success } = await updateIfUnchanged(bucket, key, next, currentEtag);
    if (success) return true;

    // Exponential backoff before retry
    await scheduler.wait(50 * 2 ** attempt);
  }

  return false; // gave up
}
```

## Object Tagging at Upload Time

```typescript
// src/tagged-upload.ts
interface UploadOptions {
  key: string;
  body: ReadableStream | ArrayBuffer | string;
  contentType: string;
  tags: Record<string, string>; // max 10 tags; keys ≤ 128 B, values ≤ 256 B
  metadata?: Record<string, string>;
}

export async function uploadTagged(
  bucket: R2Bucket,
  opts: UploadOptions,
): Promise<R2Object> {
  // Validate tag limits
  const tagEntries = Object.entries(opts.tags);
  if (tagEntries.length > 10) throw new Error("R2 allows at most 10 tags per object");

  return bucket.put(opts.key, opts.body, {
    httpMetadata:   { contentType: opts.contentType },
    customMetadata: opts.metadata ?? {},
    // Tags are passed via the R2 Workers API as a plain object
    // The runtime encodes them as x-amz-tagging on the underlying S3 call
    tags: opts.tags,
  });
}

// Example: tag an invoice PDF for lifecycle targeting
async function storeInvoice(bucket: R2Bucket, invoiceId: string, pdf: ArrayBuffer) {
  return uploadTagged(bucket, {
    key:         `invoices/${invoiceId}.pdf`,
    body:        pdf,
    contentType: "application/pdf",
    tags: {
      env:        "production",
      category:   "invoice",
      year:       String(new Date().getFullYear()),
      retention:  "7y",
    },
    metadata: {
      invoiceId,
      createdAt: new Date().toISOString(),
    },
  });
}
```

## Reading and Updating Tags

```typescript
// src/tag-ops.ts

/** Read only the tags of an object — no body transfer. */
export async function getObjectTags(
  bucket: R2Bucket,
  key: string,
): Promise<Record<string, string> | null> {
  const head = await bucket.head(key);
  if (!head) return null;
  // Tags are returned on the R2Object metadata; access via the raw response
  // in the Workers API, tags are available as head.customMetadata when set
  // via the S3 API, but the Workers API exposes them on the object directly.
  return (head as R2Object & { tags?: Record<string, string> }).tags ?? {};
}

/** Replace all tags on an existing object. R2 has no PATCH for tags — use put copy. */
export async function replaceObjectTags(
  bucket: R2Bucket,
  key: string,
  newTags: Record<string, string>,
): Promise<void> {
  // Copy object over itself with new tags — preserves body and customMetadata
  await bucket.put(key, bucket.get(key).then((o) => o!.body), {
    onlyIf: undefined, // unconditional
    tags: newTags,
  } as R2PutOptions);
}
```

## Filtering Objects by Tag in Lifecycle Rules (wrangler.toml)

```toml
# Expire any invoice object tagged retention=1y after 365 days
[[r2_buckets]]
binding     = "BUCKET"
bucket_name = "my-bucket"

# Lifecycle rules are configured via the dashboard or API, not wrangler.toml directly.
# Use the Cloudflare API to set them:
#
# POST /accounts/{account_id}/r2/buckets/{bucket_name}/lifecycle
# {
#   "rules": [
#     {
#       "id": "expire-short-retention",
#       "filter": { "prefix": "invoices/", "tag": { "key": "retention", "value": "1y" } },
#       "expiration": { "days": 365 },
#       "enabled": true
#     }
#   ]
# }
```

```typescript
// src/set-lifecycle.ts — idempotent lifecycle rule upsert
async function setTaggedLifecycleRule(
  accountId: string,
  bucketName: string,
  apiToken: string,
): Promise<void> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${accountId}/r2/buckets/${bucketName}/lifecycle`;
  const res = await fetch(url, {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${apiToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      rules: [
        {
          id: "expire-short-retention-invoices",
          filter: { prefix: "invoices/", tag: { key: "retention", value: "1y" } },
          expiration: { days: 365 },
          enabled: true,
        },
        {
          id: "expire-long-retention-invoices",
          filter: { prefix: "invoices/", tag: { key: "retention", value: "7y" } },
          expiration: { days: 2557 }, // ~7 years
          enabled: true,
        },
      ],
    }),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Failed to set lifecycle rule: ${res.status} ${body}`);
  }
}
```

## Anti-patterns

- Using `customMetadata` as a tag substitute in lifecycle rules — lifecycle and event
  notification filters only work on the `tags` field, not `customMetadata`.
- Treating a `null` return from conditional `get` as "object missing" — `null` means the
  condition was not met (ETag matched), not that the key doesn't exist; use `head()` to
  distinguish the two cases.
- Setting more than 10 tags — R2 silently rejects the upload with a validation error; the
  Workers binding throws at runtime.
- Using `etagMatches` on a multipart-uploaded object — ETag for multipart uploads is not the
  MD5 of the body; it is a composite hash. Conditional writes based on ETag still work
  correctly, but avoid comparing the ETag value itself against an externally computed MD5.

## Gotchas

- `uploadedBefore` / `uploadedAfter` compare against the `uploaded` field (the time R2
  completed the write), not a custom timestamp in `customMetadata`.
- Tags set via the Workers API are reflected in S3-compatible API calls as
  `x-amz-tagging: key=value&key2=value2`; the encoding follows percent-encoding rules.
- The R2 Workers binding does not expose a dedicated `putObjectTagging` method (unlike the S3
  API's `PUT Object tagging`); updating tags requires a full copy-over-self, which resets
  the `uploaded` timestamp.
- Conditional `put` failures do not return the current ETag in the error — call `head()` after
  a `PreconditionFailed` to retrieve the winner's ETag for the next attempt.

## Verification

```bash
# Upload an object with tags using wrangler
wrangler r2 object put my-bucket/test.json \
  --file ./test.json \
  --content-type application/json

# List objects and check tags via S3-compatible API
aws s3api get-object-tagging \
  --bucket my-bucket --key test.json \
  --endpoint-url https://<account-id>.r2.cloudflarestorage.com

# Verify a conditional GET returns null for unchanged ETag
curl -s -o /dev/null -w "%{http_code}" \
  -H 'If-None-Match: "<known-etag>"' \
  https://pub-<id>.r2.dev/test.json
# 304 Not Modified
```

## Related

- `r2-best-practices.md`
- `r2-lifecycle-rules.md`
- `r2-event-notifications.md`
- `r2-object-lifecycle-multipart.md`
- `r2-large-file-patterns.md`

## Sources

- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://developers.cloudflare.com/r2/buckets/object-lifecycles/
- https://developers.cloudflare.com/r2/api/s3/api/#putobjecttagging
