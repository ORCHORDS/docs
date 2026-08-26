# kv-metadata-size-limit

**Issue:** Cloudflare KV metadata is limited to 1024 bytes; exceeding this limit throws a silent error or truncates data
**Date:** 2026-08-11
**Status:** documented

## Symptom
A KV `put` call with a large metadata object succeeds silently but the stored metadata is truncated or the call throws `KV PUT failed: metadata too large`. Subsequent reads return `null` metadata or partial data.

## Root cause
Cloudflare KV enforces a 1024-byte limit on the metadata JSON blob. If the serialized metadata string exceeds this, the write fails. This limit is easy to hit when storing arrays of tags, long descriptions, or nested objects as metadata.

## Fix
Keep metadata minimal — store only index/filter fields needed for listing. Move large data into the KV value itself:
```ts
// Too large in metadata
await env.KV.put(key, value, {
  metadata: { tags: [...500chars], description: '...600chars' }, // > 1024 bytes
});

// Fixed — move large fields to value
await env.KV.put(key, JSON.stringify({ ...data, tags, description }), {
  metadata: { contentType: 'application/json', updatedAt: Date.now() },
});
```

## Detection
```ts
const meta = JSON.stringify(yourMetadata);
if (meta.length > 1024) console.warn('Metadata too large:', meta.length);
```

## Related
- `r2-etag-conditional-request.md`
- `worker-memory-limit-exceeded.md`
