# R2 Conditional GET ETag Bandwidth Savings

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

A Workers endpoint serves objects from R2 (assets, data exports, large JSON configs) and re-downloads the full object from R2 on every request, even when the object has not changed. R2 egress from the bucket to the Worker counts toward R2 operation costs, and forwarding unchanged payloads to clients wastes bandwidth and increases response latency. You want to respond with `304 Not Modified` when the client already has a valid copy, and avoid re-fetching from R2 at all when possible.

---

## Context

R2 assigns an **ETag** to every object at upload time. The ETag is the MD5 hex digest of the object body (for single-part uploads) or a compound digest for multipart uploads. R2 returns this value in the `ETag` response header on every `GET` or `HEAD`.

The HTTP conditional GET mechanism works as follows:

- Client sends `If-None-Match: "<etag>"` (or `If-None-Match: *`).
- Server compares the provided ETag against the stored ETag.
- If they match, the server returns `304 Not Modified` with no body.
- If they differ, the server returns `200 OK` with the full body.

R2's S3-compatible API honours `If-None-Match` natively when accessed via the S3 binding or the `fetch()` S3-compatible endpoint. The Workers R2 binding (`env.BUCKET.get()`) requires you to pass the condition explicitly via `R2GetOptions`.

This pattern eliminates redundant R2-to-Worker data transfer and — combined with proper `Cache-Control` and `ETag` forwarding — enables browser-native conditional revalidation, saving both bandwidth and R2 read operation costs.

---

## Reading the ETag from R2

```typescript
interface Env {
  BUCKET: R2Bucket;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const key = url.pathname.slice(1); // strip leading "/"

    // HEAD the object first to get its ETag cheaply (no body transfer).
    const head = await env.BUCKET.head(key);
    if (!head) return new Response("Not Found", { status: 404 });

    const objectEtag = head.httpEtag; // e.g. '"d41d8cd98f00b204e9800998ecf8427e"'

    // Check the client's cached ETag.
    const clientEtag = request.headers.get("If-None-Match");
    if (clientEtag && clientEtag === objectEtag) {
      return new Response(null, {
        status: 304,
        headers: {
          ETag: objectEtag,
          "Cache-Control": "public, max-age=0, must-revalidate",
        },
      });
    }

    // Full fetch only when necessary.
    const object = await env.BUCKET.get(key);
    if (!object) return new Response("Not Found", { status: 404 });

    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set("ETag", object.httpEtag);
    headers.set("Cache-Control", "public, max-age=0, must-revalidate");

    return new Response(object.body, { status: 200, headers });
  },
};
```

---

## Using R2GetOptions to Push Conditional Logic into R2

Instead of a separate `head()` call, pass `If-None-Match` directly into `env.BUCKET.get()`. R2 returns `null` (object unchanged) or the full object — no extra round-trip.

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const key = new URL(request.url).pathname.slice(1);
    const clientEtag = request.headers.get("If-None-Match");

    const object = await env.BUCKET.get(key, {
      onlyIf: clientEtag
        ? { etagDoesNotMatch: clientEtag } // fetch only if etag changed
        : undefined,
    });

    // R2 returns null when onlyIf condition is not met (i.e., ETag matches).
    if (!object) {
      // Must still read the metadata to build a valid 304.
      const head = await env.BUCKET.head(key);
      if (!head) return new Response("Not Found", { status: 404 });

      return new Response(null, {
        status: 304,
        headers: {
          ETag: head.httpEtag,
          "Cache-Control": "public, max-age=0, must-revalidate",
          "Last-Modified": head.uploaded.toUTCString(),
        },
      });
    }

    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set("ETag", object.httpEtag);
    headers.set("Cache-Control", "public, max-age=0, must-revalidate");
    headers.set("Last-Modified", object.uploaded.toUTCString());

    return new Response(object.body, { headers });
  },
};
```

---

## Storing and Forwarding Custom ETags

For objects whose content is computed rather than stored verbatim, or where you want a logical ETag independent of the raw R2 MD5 (e.g., version-tagged releases), store a custom ETag in R2 object metadata.

```typescript
// On upload: attach a semantic version ETag
await env.BUCKET.put("config/app.json", jsonBody, {
  httpMetadata: {
    contentType: "application/json",
    cacheControl: "public, max-age=0, must-revalidate",
  },
  customMetadata: {
    "x-semantic-version": "2026-08-23T10:00:00Z",
  },
});

// On serve: use the semantic version as the ETag
async function serveWithSemanticEtag(
  request: Request,
  env: Env,
  key: string
): Promise<Response> {
  const head = await env.BUCKET.head(key);
  if (!head) return new Response("Not Found", { status: 404 });

  const semanticEtag = `"${head.customMetadata?.["x-semantic-version"] ?? head.etag}"`;
  const clientEtag = request.headers.get("If-None-Match");

  if (clientEtag === semanticEtag) {
    return new Response(null, { status: 304, headers: { ETag: semanticEtag } });
  }

  const object = await env.BUCKET.get(key);
  if (!object) return new Response("Not Found", { status: 404 });

  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set("ETag", semanticEtag);

  return new Response(object.body, { headers });
}
```

---

## Caching ETags in KV to Avoid Repeated R2 HEAD Calls

For high-traffic endpoints, a `head()` per request is expensive. Cache the ETag in KV with a short TTL to avoid per-request R2 operations.

```typescript
interface Env {
  BUCKET: R2Bucket;
  META_CACHE: KVNamespace;
}

const ETAG_TTL_SECONDS = 30;

async function getCachedEtag(env: Env, key: string): Promise<string | null> {
  return env.META_CACHE.get(`etag:${key}`);
}

async function refreshEtag(env: Env, key: string): Promise<string | null> {
  const head = await env.BUCKET.head(key);
  if (!head) return null;
  await env.META_CACHE.put(`etag:${key}`, head.httpEtag, {
    expirationTtl: ETAG_TTL_SECONDS,
  });
  return head.httpEtag;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const key = new URL(request.url).pathname.slice(1);
    const clientEtag = request.headers.get("If-None-Match");

    let currentEtag = await getCachedEtag(env, key);
    if (!currentEtag) currentEtag = await refreshEtag(env, key);
    if (!currentEtag) return new Response("Not Found", { status: 404 });

    if (clientEtag === currentEtag) {
      return new Response(null, { status: 304, headers: { ETag: currentEtag } });
    }

    const object = await env.BUCKET.get(key);
    if (!object) return new Response("Not Found", { status: 404 });

    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set("ETag", object.httpEtag);
    headers.set("Cache-Control", "public, max-age=0, must-revalidate");

    // Refresh KV if the R2 ETag has changed (e.g., object was replaced).
    if (object.httpEtag !== currentEtag) {
      await env.META_CACHE.put(`etag:${key}`, object.httpEtag, {
        expirationTtl: ETAG_TTL_SECONDS,
      });
    }

    return new Response(object.body, { headers });
  },
};
```

---

## Weak vs Strong ETag Semantics

R2 returns strong ETags (`"abc123"`). Weak ETags (`W/"abc123"`) signal that the representation is semantically equivalent but may differ byte-for-byte (e.g., compressed vs uncompressed). Use weak ETags when content negotiation (Accept-Encoding) or on-the-fly transforms change the body.

```typescript
function toWeakEtag(strongEtag: string): string {
  // Convert `"abc"` → `W/"abc"`
  return strongEtag.startsWith('W/') ? strongEtag : `W/${strongEtag}`;
}

// Weak ETag comparison (strip W/ prefix and quotes before comparing)
function etagsMatch(a: string, b: string): boolean {
  const normalize = (e: string) => e.replace(/^W\//, '').replace(/"/g, '');
  return normalize(a) === normalize(b);
}
```

---

## Anti-patterns

- **Stripping the ETag before forwarding to the client.** If the Worker consumes the R2 object but does not forward the `ETag` header, the client can never revalidate and will always receive the full body.
- **Using `If-None-Match: *` for conditional GETs.** The `*` wildcard means "send 304 only if the object exists at all," not "send 304 only if unchanged." Always pass the specific ETag value.
- **Applying conditional GET to mutable keys without invalidating KV.** If an object is replaced under the same key and the old ETag is cached in KV, clients will receive stale 304 responses until the KV TTL expires. Lower the TTL or invalidate the KV entry on upload.
- **Serving ETags for range responses without byte-range awareness.** RFC 7232 requires that a 304 response to a range request include the full-object ETag, not a partial ETag. R2 handles this correctly for its own range responses.

---

## Gotchas

- **R2 multipart ETag format.** Multipart-uploaded objects get a compound ETag like `"etag-N"` (number of parts). This is an MD5 of the concatenated part ETags, not the full-object MD5. Do not attempt to recompute it client-side.
- **ETag case sensitivity.** HTTP ETags are case-sensitive. Always compare them byte-for-byte without normalisation.
- **R2 `get()` with `onlyIf: { etagDoesNotMatch }` returns `null` for two distinct reasons:** the condition was not met (object unchanged), OR the key does not exist. You must distinguish these cases — the example above uses a fallback `head()` call.
- **Cloudflare cache layer and ETags.** When a Worker response passes through Cloudflare's cache (`Cache-Control: public`), Cloudflare stores the ETag and handles `If-None-Match` revalidation itself on subsequent cache hits. Ensure your Worker forwards the ETag or the cache layer cannot revalidate.

---

## Verification

```typescript
// Verify conditional GET path is working — measure 304 rate
let total = 0;
let notModified = 0;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    total++;
    const response = await handleRequest(request, env);
    if (response.status === 304) notModified++;

    if (total % 500 === 0) {
      console.log(JSON.stringify({
        "304_rate": notModified / total,
        total_requests: total,
      }));
    }
    return response;
  },
};
```

In Cloudflare Analytics, compare `r2_read_bytes` (in the R2 metrics dashboard) before and after deploying conditional GET support. A well-adopted ETag workflow should reduce R2 egress by 40–80 % on assets that change infrequently.

---

## Related

- `etag-conditional-requests.md`
- `r2-multipart-upload-performance.md`
- `r2-range-request-large-file-optimization.md`
- `cache-control-headers.md`
- `cloudflare-r2-presigned-cdn-acceleration.md`

---

## Sources

- Cloudflare R2 Workers binding: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- RFC 7232 — Conditional Requests: https://www.rfc-editor.org/rfc/rfc7232
- R2 ETag semantics: https://developers.cloudflare.com/r2/objects/etag/
- HTTP 304 Not Modified: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/304
