# r2-best-practices

**Issue:** R2 best practices — uploads, lifecycle, costs
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your R2 bill is high. You look at the dashboard. Most
of the cost is "Class A operations" (writes). You
rewrite the same object 10 times. You could combine.

## Root cause
**R2 has pricing tiers.** Optimize for them.

**Source:** R2 pricing:
https://developers.cloudflare.com/r2/pricing/

## R2 pricing

- **Storage:** $0.015/GB/mo
- **Class A (write):** $4.50/M
- **Class B (read):** $0.36/M
- **Egress:** Free

For high-write apps, optimize writes.

## The "presigned URL" pattern

For uploads, use presigned URLs:
```ts
// 1. Server generates the URL
const url = await env.R2!.createPresignedUrl({
  key: `uploads/${userId}/${fileName}`,
  expiration: 3600,
  method: 'PUT',
});

// 2. Client uploads directly
await fetch(url, { method: 'PUT', body: file });
```

The upload is direct (no Worker).

## The "multipart" pattern

For large files, use multipart:
```ts
// 1. Create multipart
const multipart = await env.R2!.createMultipartUpload({
  key: `uploads/${userId}/${fileName}`,
});

// 2. Per part
const partCount = Math.ceil(file.size / (5 * 1024 * 1024));
for (let i = 0; i < partCount; i++) {
  const partUrl = await env.R2!.createPresignedUrl({
    key: multipart.key,
    expiration: 3600,
    method: 'PUT',
    partNumber: i + 1,
    uploadId: multipart.uploadId,
  });
  // Client uploads each part
}

// 3. Complete
await multipart.complete(parts);
```

The large file is in parts.

## The "lifecycle" pattern

For lifecycle, move cold data:
- **Standard:** Frequently accessed
- **Infrequent Access:** Monthly accessed
- **Archive:** Yearly accessed

```toml
# wrangler.toml
[[r2_buckets]]
binding = "R2"
bucket_name = "my-bucket"
lifecycle_rules = [
  { id = "archive-old", enabled = true, condition = { age = 90 }, action = { type = "Transition", storage_class = "InfrequentAccess" } },
]
```

The lifecycle is configured.

## The "cache" pattern

For R2 reads, cache via CF:
```ts
async function getR2Cached(key: string, env: Env): Promise<Response> {
  const cached = await caches.default.match(`https://r2.example.com/${key}`);
  if (cached) return cached;

  const obj = await env.R2!.get(key);
  if (!obj) return new Response('Not found', { status: 404 });

  const response = new Response(obj.body, {
    headers: { 'cache-control': 'public, max-age=86400' },
  });
  await caches.default.put(`https://r2.example.com/${key}`, response.clone());
  return response;
}
```

The R2 read is cached.

## The "metadata" pattern

For metadata, store in R2:
```ts
await env.R2!.put('config.json', JSON.stringify(config), {
  httpMetadata: { contentType: 'application/json' },
  customMetadata: {
    version: '1.0.0',
    environment: 'production',
  },
});
```

The metadata is per object.

## The "versioning" pattern

For versioning, enable per bucket:
```toml
[[r2_buckets]]
binding = "R2"
bucket_name = "my-bucket"
# Versioning is set in the dashboard
```

The old versions are kept.

## The "CORS" pattern

For CORS on R2:
```toml
[[r2_buckets]]
binding = "R2"
bucket_name = "my-bucket"
# CORS is set in the dashboard
```

The CORS is configured.

## The "R2 + Workers" pattern

For R2 binding:
```ts
const obj = await env.R2!.get('users/u_123.json');
const text = await obj!.text();
```

The binding is used.

## The "R2 + D1" pattern

For D1 + R2:
- **D1:** Metadata
- **R2:** File content

```ts
// 1. Store metadata in D1
await env.DB!.prepare(
  `INSERT INTO files (id, r2_key, name, size) VALUES (?, ?, ?, ?)`
).bind(id, key, name, size).run();

// 2. Store content in R2
await env.R2!.put(key, file);

// 3. Read
const meta = await env.DB!.prepare(`SELECT * FROM files WHERE id = ?`).bind(id).first();
const obj = await env.R2!.get(meta.r2Key);
```

The data is split.

## The "R2 + Workers Cache API" pattern

For Worker-side cache:
```ts
const cache = caches.default;
const cached = await cache.match(request);
if (cached) return cached;

const obj = await env.R2!.get(key);
const response = new Response(obj!.body);
await cache.put(request, response.clone());
return response;
```

The R2 read is cached at the edge.

## The "R2 observability" pattern

For observability:
- **Storage:** Total bytes
- **Class A:** Writes per minute
- **Class B:** Reads per minute
- **Egress:** Per object

The metrics are in the CF dashboard.

## The "R2 anti-pattern" anti-patterns

### 1. Upload through Worker
- **Issue:** Worker timeout for large files
- **Fix:** Presigned URL

### 2. No multipart for large files
- **Issue:** Connection drops = restart
- **Fix:** Multipart

### 3. No lifecycle
- **Issue:** Cold data costs
- **Fix:** Lifecycle to IA / Archive

### 4. No cache
- **Issue:** Repeat reads
- **Fix:** Cache via CF

### 5. SELECT * in metadata
- **Issue:** Over-fetch
- **Fix:** SELECT specific columns

## Verification
- **Test:** Upload works
- **Test:** Multipart works
- **Test:** Cache works
- **Live:** R2 metrics monitored
- **Audit:** Quarterly review

## Gotchas
- **The "upload through Worker" anti-pattern.** Use
  presigned URL.
- **The "no multipart" anti-pattern.** Use multipart.
- **The "no lifecycle" anti-pattern.** Configure.

## Related
- `cloudflare/r2-large-file-patterns.md`
- `cloudflare/r2-signed-urls.md`
- `cloudflare/r2-multipart-upload.md`
- `feature-cookbook-file-upload.md`
- R2 docs: https://developers.cloudflare.com/r2/
- R2 pricing: https://developers.cloudflare.com/r2/pricing/
