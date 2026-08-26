# Zero-Downtime R2 Bucket Migration

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

You need to move objects between R2 buckets — renaming a bucket, transferring to a different Cloudflare account, splitting a monolithic bucket by environment, or reorganising key prefixes — without interrupting a live application that continuously reads and writes to R2.

A direct bucket rename is not possible in R2 (unlike S3 which also lacks native rename). A naive copy-and-swap creates a window where writes go to the old bucket but reads query the new one, or vice versa. Objects written after the copy started are silently lost.

---

## Context

R2 does not support bucket-level replication between accounts (as of mid-2026). Within the same account, R2 Sippy (migration assistant) can replicate from S3-compatible sources during migration but is not designed for bucket-to-bucket within the same account. The canonical approach is a proxy-write pattern driven by a Worker sitting in front of both buckets, combined with a background copy job.

Key constraints:

- R2 pricing counts Class A operations (PUT, DELETE) and Class B operations (GET, HEAD) — the migration job will accrue real cost at scale.
- Worker CPU limits (50 ms unbound on free; unlimited on Paid when using `no_bundle` or Durable Object context) affect how much work a single invocation can do.
- R2 object metadata and custom headers must be explicitly copied; they are not preserved automatically.
- Multipart uploads in progress on the source bucket at the time of cutover need special handling.

---

## Phase 1 — Dual-Write Proxy

Deploy a Worker that intercepts all R2 operations. Writes go to both buckets; reads serve from the new bucket with fallback to the old one. This ensures no write is lost from the moment the proxy goes live.

```toml
# wrangler.toml
name = "r2-migration-proxy"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[r2_buckets]]
binding = "BUCKET_OLD"
bucket_name = "assets-prod"

[[r2_buckets]]
binding = "BUCKET_NEW"
bucket_name = "assets-prod-v2"

[vars]
MIGRATION_PHASE = "dual-write"   # "dual-write" | "new-primary" | "complete"
```

```typescript
// src/index.ts
export interface Env {
  BUCKET_OLD: R2Bucket;
  BUCKET_NEW: R2Bucket;
  MIGRATION_PHASE: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const key = url.pathname.slice(1);  // strip leading slash

    if (request.method === "PUT" || request.method === "POST") {
      return handleWrite(request, key, env);
    }
    if (request.method === "DELETE") {
      return handleDelete(key, env);
    }
    return handleRead(request, key, env);
  },
};

async function handleWrite(
  request: Request,
  key: string,
  env: Env,
): Promise<Response> {
  const body = await request.arrayBuffer();
  const headers = Object.fromEntries(request.headers.entries());
  const contentType = headers["content-type"] ?? "application/octet-stream";

  // Always write to new bucket first — it is the future primary
  await env.BUCKET_NEW.put(key, body, {
    httpMetadata: { contentType },
    customMetadata: extractCustomMetadata(headers),
  });

  // Dual-write to old bucket only during migration phase
  if (env.MIGRATION_PHASE === "dual-write") {
    await env.BUCKET_OLD.put(key, body, {
      httpMetadata: { contentType },
      customMetadata: extractCustomMetadata(headers),
    });
  }

  return new Response(null, { status: 200 });
}

async function handleRead(
  request: Request,
  key: string,
  env: Env,
): Promise<Response> {
  // Try new bucket; fall back to old during migration
  let object = await env.BUCKET_NEW.get(key);
  if (!object && env.MIGRATION_PHASE !== "complete") {
    object = await env.BUCKET_OLD.get(key);
  }
  if (!object) return new Response("Not Found", { status: 404 });

  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set("etag", object.httpEtag);
  return new Response(object.body, { headers });
}

async function handleDelete(key: string, env: Env): Promise<Response> {
  await env.BUCKET_NEW.delete(key);
  if (env.MIGRATION_PHASE === "dual-write") {
    await env.BUCKET_OLD.delete(key);
  }
  return new Response(null, { status: 204 });
}

function extractCustomMetadata(
  headers: Record<string, string>,
): Record<string, string> {
  return Object.fromEntries(
    Object.entries(headers)
      .filter(([k]) => k.startsWith("x-amz-meta-") || k.startsWith("x-custom-"))
      .map(([k, v]) => [k.replace(/^x-amz-meta-/, ""), v]),
  );
}
```

---

## Phase 2 — Background Copy Job

While dual-write is active, copy all pre-existing objects from old to new. Use a Cron Trigger + KV cursor to make the copy job resumable across the 30-second Worker timeout.

```typescript
// src/copy-job.ts — runs on a Cron Trigger every minute
export interface CopyEnv extends Env {
  COPY_STATE: KVNamespace;  // stores cursor + stats
}

export async function scheduledCopy(env: CopyEnv): Promise<void> {
  const cursor = (await env.COPY_STATE.get("cursor")) ?? undefined;
  const stats = JSON.parse((await env.COPY_STATE.get("stats")) ?? "{}");

  const listed = await env.BUCKET_OLD.list({
    cursor,
    limit: 100,  // tune: 100 objects × average size must finish well under 25s
  });

  const copies = listed.objects.map(async (obj) => {
    // Skip if already exists in new bucket (idempotent)
    const existing = await env.BUCKET_NEW.head(obj.key);
    if (existing?.etag === obj.etag) return;

    const source = await env.BUCKET_OLD.get(obj.key);
    if (!source) return;

    await env.BUCKET_NEW.put(obj.key, source.body, {
      httpMetadata: source.httpMetadata,
      customMetadata: source.customMetadata,
      sha256: obj.checksums?.sha256,  // integrity check
    });
  });

  await Promise.allSettled(copies);

  if (listed.truncated) {
    await env.COPY_STATE.put("cursor", listed.cursor!);
    await env.COPY_STATE.put("stats", JSON.stringify({
      ...stats,
      copied: (stats.copied ?? 0) + listed.objects.length,
    }));
  } else {
    // Copy complete — remove cursor, record finish time
    await env.COPY_STATE.delete("cursor");
    await env.COPY_STATE.put("stats", JSON.stringify({
      ...stats,
      finished: new Date().toISOString(),
      total: (stats.copied ?? 0) + listed.objects.length,
    }));
  }
}
```

---

## Phase 3 — Cutover

Once the copy job reports `finished` in KV and the object counts match, flip `MIGRATION_PHASE` to `"new-primary"`. Reads and writes now go exclusively to the new bucket. The old bucket stays live but receives no traffic.

```bash
# Verify object counts match before cutover
wrangler r2 object list assets-prod --remote | wc -l
wrangler r2 object list assets-prod-v2 --remote | wc -l

# Update the Worker env var to flip the read path
wrangler secret put MIGRATION_PHASE --env production
# Enter: new-primary
wrangler deploy --env production
```

After 24-48 hours of clean operation in `new-primary` mode, flip to `"complete"` and disable the copy job. Old bucket can be deleted after a retention window.

---

## Phase 4 — Client URL Migration (if bucket name is public)

If clients reference the old bucket URL directly (e.g. via a `pub.r2.dev` URL or custom domain pointed at the old bucket), update the DNS `CNAME` or `Worker Route` to the new bucket before deleting the old bucket. Keep the old `pub.r2.dev` bucket alive as a redirect worker if the public URL cannot change:

```typescript
// Redirect worker for legacy public URL
export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const newUrl = `https://assets-prod-v2.example.com${url.pathname}`;
    return Response.redirect(newUrl, 301);
  },
};
```

---

## Anti-patterns

- **Copy-then-swap without dual-write**: creates a write-loss window. Objects written between the final copy sweep and the DNS/config flip are lost.
- **Listing without cursor persistence**: if the copy Worker times out mid-list, restarting from the beginning re-copies everything and may miss objects added near the end.
- **Ignoring multipart uploads**: in-flight multipart uploads to the old bucket after dual-write starts may not be visible until completed; do not delete the old bucket until all multipart uploads have completed or been aborted.
- **Relying on `etag` equality for large objects**: R2 and S3 compute etags differently for multipart objects (composite MD5). Use `checksums.sha256` when available, or compare object size + last-modified.
- **Forgetting custom metadata**: `r2.put()` requires explicit `customMetadata` pass-through; metadata is not carried automatically when you stream `source.body` to the new bucket.

---

## Gotchas

- R2 `list()` returns a maximum of 1000 objects per call regardless of the `limit` parameter. Paginate with the returned `cursor`.
- `BUCKET_OLD.get(key)` returns a `ReadableStream` body. Once consumed in the copy path, it cannot be re-read. Copy the stream to an `ArrayBuffer` first if you need the body more than once.
- Worker `wrangler.toml` bindings for R2 must use unique `binding` names. You cannot bind the same bucket twice to inspect both old and new from one Worker during the transition.
- KV `put` is eventually consistent. Do not use KV to signal "copy complete" to a Worker that reads KV in the same request — read-after-write consistency is not guaranteed; use a Durable Object or a dedicated coordination Worker if strict ordering is needed.
- Pricing: 1 million Class B (read) operations on the old bucket + 1 million Class A (write) operations on the new bucket are incurred for each million objects copied. Budget accordingly for large buckets.

---

## Verification

```bash
# Count objects in both buckets after copy completes
OLD_COUNT=$(wrangler r2 object list assets-prod --remote --json | jq '. | length')
NEW_COUNT=$(wrangler r2 object list assets-prod-v2 --remote --json | jq '. | length')
echo "Old: $OLD_COUNT  New: $NEW_COUNT"
[ "$OLD_COUNT" = "$NEW_COUNT" ] && echo "MATCH" || echo "MISMATCH — do not cutover"

# Sample 50 random keys and compare checksums
wrangler r2 object list assets-prod-v2 --remote --json \
  | jq -r '.[].key' | shuf | head -50 \
  | while read key; do
      old_etag=$(wrangler r2 object head "assets-prod/$key" --remote --json | jq -r '.etag')
      new_etag=$(wrangler r2 object head "assets-prod-v2/$key" --remote --json | jq -r '.etag')
      [ "$old_etag" = "$new_etag" ] || echo "MISMATCH: $key  old=$old_etag new=$new_etag"
    done
```

---

## Related

- `durable-objects-namespace-migration-zero-downtime.md`
- `zero-downtime-database-migrations.md`
- `rollback-strategies-workers-pages.md`
- `workers-service-bindings-deployment-ordering.md`

---

## Sources

- Cloudflare R2 documentation — Object storage, list API, multipart uploads (developers.cloudflare.com/r2)
- Cloudflare Workers documentation — R2 bindings (developers.cloudflare.com/workers/runtime-apis/r2)
- Cloudflare R2 Sippy documentation — migration from S3 (developers.cloudflare.com/r2/data-migration/sippy)
- Cloudflare KV documentation — consistency model (developers.cloudflare.com/kv)
