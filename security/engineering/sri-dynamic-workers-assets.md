# Subresource Integrity for Dynamically Generated Workers Assets

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

Your Cloudflare Worker renders HTML server-side and injects `<script>` or `<link>` tags for assets whose content or URLs are determined at request time — for example, a per-tenant JS bundle selected from KV, an inline nonce-protected style block assembled from feature flags, or a third-party script whose URL is stored in D1. You cannot hard-code SRI hashes in source because the content is dynamic. You need to compute `integrity` attribute hashes at the edge and attach them to each tag before the HTML leaves the Worker.

---

## Context

Subresource Integrity (SRI) allows browsers to verify that a fetched resource has not been tampered with in transit or at the CDN layer. The `integrity` attribute contains a base64-encoded cryptographic hash (SHA-256, SHA-384, or SHA-512) of the expected resource content. If the browser's computed hash does not match, it refuses to execute the script or apply the stylesheet.

Static SRI — where hashes are baked into HTML templates at build time — is straightforward. Dynamic SRI requires computing the hash at the edge, which involves:

1. Fetching or reading the resource content.
2. Hashing it with the Web Crypto API (`SubtleCrypto.digest`).
3. Base64-encoding the raw digest.
4. Injecting `integrity="sha384-<hash>"` into the tag.

Workers have full access to the Web Crypto API via `crypto.subtle`, making this viable at the edge with no native modules.

**When to cache the hash:** Hashing is O(size of asset). For large assets fetched on every request, cache the hash in KV keyed by content hash or ETag to avoid redundant computation.

---

## Computing an SRI Hash with SubtleCrypto

```typescript
// src/sri/hash.ts

type SriAlgorithm = 'sha-256' | 'sha-384' | 'sha-512';

const ALGO_PREFIX: Record<SriAlgorithm, string> = {
  'sha-256': 'sha256',
  'sha-384': 'sha384',
  'sha-512': 'sha512',
};

/**
 * Compute an SRI hash for the given content.
 * @param content - Raw bytes or string of the resource
 * @param algorithm - Hash algorithm; prefer sha-384 per W3C recommendation
 * @returns integrity attribute value, e.g. "sha384-<base64>"
 */
export async function computeSri(
  content: string | ArrayBuffer,
  algorithm: SriAlgorithm = 'sha-384'
): Promise<string> {
  const encoded =
    typeof content === 'string'
      ? new TextEncoder().encode(content)
      : new Uint8Array(content);

  const digest = await crypto.subtle.digest(algorithm.toUpperCase(), encoded);
  const base64 = btoa(String.fromCharCode(...new Uint8Array(digest)));

  return `${ALGO_PREFIX[algorithm]}-${base64}`;
}

/**
 * Compute multiple SRI hashes and return a space-separated integrity value.
 * Browsers accept the first matching algorithm they support.
 */
export async function computeMultiSri(
  content: string | ArrayBuffer,
  algorithms: SriAlgorithm[] = ['sha-384', 'sha-512']
): Promise<string> {
  const hashes = await Promise.all(
    algorithms.map(algo => computeSri(content, algo))
  );
  return hashes.join(' ');
}
```

---

## Fetching Remote Assets and Attaching Integrity

```typescript
// src/sri/fetch-with-integrity.ts
import { computeSri } from './hash';

export interface IntegrityFetchResult {
  content: string;
  contentType: string;
  integrity: string;
  url: string;
}

/**
 * Fetch a remote script/stylesheet and compute its SRI hash.
 * Validates that the response is cacheable (has ETag or Last-Modified)
 * so we can safely cache the hash.
 */
export async function fetchWithIntegrity(
  url: string,
  algorithm: 'sha-256' | 'sha-384' | 'sha-512' = 'sha-384'
): Promise<IntegrityFetchResult> {
  // Enforce HTTPS — never compute SRI over HTTP (MITM trivially defeats it)
  const parsed = new URL(url);
  if (parsed.protocol !== 'https:') {
    throw new Error(`SRI fetch requires HTTPS; got ${parsed.protocol}`);
  }

  const response = await fetch(url, {
    cf: { cacheTtl: 300 }, // cache at edge for 5 min
  });

  if (!response.ok) {
    throw new Error(
      `Failed to fetch ${url}: ${response.status} ${response.statusText}`
    );
  }

  const contentType = response.headers.get('content-type') ?? '';
  const body = await response.text();
  const integrity = await computeSri(body, algorithm);

  return { content: body, contentType, integrity, url };
}
```

---

## KV Hash Cache: Avoid Re-hashing on Every Request

```typescript
// src/sri/cache.ts
import type { KVNamespace } from '@cloudflare/workers-types';
import { computeSri } from './hash';

const CACHE_TTL_SECONDS = 3600; // 1 hour; tune to your asset change cadence

/**
 * Look up or compute the SRI hash for a given asset URL.
 * Cache key includes a version tag so a CDN purge or version bump
 * invalidates the cached hash.
 */
export async function cachedSri(
  kv: KVNamespace,
  assetUrl: string,
  assetContent: string,
  versionTag: string // e.g. file ETag, git commit SHA, or content-based hash
): Promise<string> {
  const cacheKey = `sri:${versionTag}:${assetUrl}`;

  const cached = await kv.get(cacheKey);
  if (cached) return cached;

  const integrity = await computeSri(assetContent, 'sha-384');
  await kv.put(cacheKey, integrity, { expirationTtl: CACHE_TTL_SECONDS });

  return integrity;
}

/**
 * Invalidate the cached SRI hash for an asset — call this from your
 * deploy pipeline after uploading a new asset version.
 */
export async function invalidateSriCache(
  kv: KVNamespace,
  assetUrl: string,
  oldVersionTag: string
): Promise<void> {
  const cacheKey = `sri:${oldVersionTag}:${assetUrl}`;
  await kv.delete(cacheKey);
}
```

---

## HTML Template: Injecting Integrity Attributes

```typescript
// src/sri/template.ts
import { computeSri } from './hash';
import type { KVNamespace } from '@cloudflare/workers-types';

export interface ScriptDescriptor {
  src: string;          // URL of the external script
  content?: string;     // pre-fetched content (skip network call if provided)
  versionTag?: string;  // for KV cache keying
  defer?: boolean;
  crossorigin?: 'anonymous' | 'use-credentials';
}

/**
 * Build a <script> tag with a valid integrity attribute.
 * Uses crossorigin="anonymous" by default — required for SRI to work
 * when the asset is served from a different origin.
 */
export async function buildScriptTag(
  descriptor: ScriptDescriptor,
  kv?: KVNamespace
): Promise<string> {
  let content = descriptor.content;

  if (!content) {
    const resp = await fetch(descriptor.src);
    if (!resp.ok) throw new Error(`Failed to fetch ${descriptor.src}`);
    content = await resp.text();
  }

  let integrity: string;

  if (kv && descriptor.versionTag) {
    const { cachedSri } = await import('./cache');
    integrity = await cachedSri(kv, descriptor.src, content, descriptor.versionTag);
  } else {
    integrity = await computeSri(content, 'sha-384');
  }

  const attrs = [
    ``,
    `integrity="${integrity}"`,
    `crossorigin="${descriptor.crossorigin ?? 'anonymous'}"`,
    descriptor.defer ? 'defer' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return `<script ${attrs}></script>`;
}

/**
 * Build a <link rel="stylesheet"> tag with integrity.
 */
export async function buildStylesheetTag(
  href: string,
  content: string,
  kv?: KVNamespace,
  versionTag?: string
): Promise<string> {
  let integrity: string;

  if (kv && versionTag) {
    const { cachedSri } = await import('./cache');
    integrity = await cachedSri(kv, href, content, versionTag);
  } else {
    integrity = await computeSri(content, 'sha-384');
  }

  return `<link rel="stylesheet"  integrity="${integrity}" crossorigin="anonymous">`;
}

function escapeAttr(value: string): string {
  return value.replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
```

---

## Worker Fetch Handler: Assembling Secure HTML

```typescript
// src/worker.ts
import { buildScriptTag, buildStylesheetTag } from './sri/template';

export interface Env {
  ASSET_KV: KVNamespace;
  TENANT_SCRIPTS: KVNamespace; // per-tenant JS bundle lookup
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const tenantId = request.headers.get('x-tenant-id') ?? 'default';

    // Retrieve tenant-specific script URL and version tag from KV
    const scriptMeta = await env.TENANT_SCRIPTS.get(`tenant:${tenantId}:script-meta`, 'json') as
      | { url: string; versionTag: string }
      | null;

    if (!scriptMeta) {
      return new Response('Tenant not found', { status: 404 });
    }

    // Fetch the script content once (in parallel with other assets)
    const [scriptResp, thirdPartyContent] = await Promise.all([
      fetch(scriptMeta.url),
      fetch('https://cdn.example.com/analytics.js'),
    ]);

    if (!scriptResp.ok || !thirdPartyContent.ok) {
      return new Response('Asset fetch failed', { status: 502 });
    }

    const [scriptContent, analyticsContent] = await Promise.all([
      scriptResp.text(),
      thirdPartyContent.text(),
    ]);

    // Build script tags with computed SRI (uses KV cache for tenant script)
    const [tenantScriptTag, analyticsTag] = await Promise.all([
      buildScriptTag(
        { src: scriptMeta.url, content: scriptContent, versionTag: scriptMeta.versionTag, defer: true },
        env.ASSET_KV
      ),
      buildScriptTag({ src: 'https://cdn.example.com/analytics.js', content: analyticsContent }),
    ]);

    const html = `<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>App</title>
  ${tenantScriptTag}
  ${analyticsTag}
</head>
<body>
  <div id="app"></div>
</body>
</html>`;

    return new Response(html, {
      headers: {
        'Content-Type': 'text/html; charset=utf-8',
        'Content-Security-Policy':
          "script-src 'self' https://cdn.example.com; require-sri-for script style",
      },
    });
  },
};
```

---

## Anti-patterns

**Computing the SRI hash from a URL without fetching the actual bytes.** The `integrity` attribute must match the bytes the browser will receive. If you hash a URL string or a stale copy, the browser will reject the resource.

**Using `sha-256` alone.** The W3C SRI specification recommends `sha-384` or `sha-512` as the minimum strength. `sha-256` is still secure but browsers may eventually deprecate it for SRI. Default to `sha-384`.

**Omitting `crossorigin="anonymous"` on cross-origin resources.** Without this attribute the browser does not perform a CORS fetch and therefore cannot compare the hash. The resource loads without SRI enforcement, defeating the purpose.

**Caching hashes without tying them to content versioning.** A KV-cached hash keyed only by URL will become stale after a CDN cache purge or asset update. Always include a version tag (ETag, content hash, commit SHA) in the cache key.

**Embedding SRI for `data:` URIs or inline scripts.** SRI only applies to external resources loaded via `src` or `href`. For inline scripts, use a CSP nonce (see `content-security-policy-workers-nonce.md`).

---

## Gotchas

**CORS must be enabled on the asset origin.** SRI enforcement requires the browser to make a CORS fetch (`crossorigin="anonymous"`). If the asset CDN does not return `Access-Control-Allow-Origin: *` (or your origin), the browser will refuse to load the resource even if the hash is correct.

**Gzip/Brotli encoding changes the bytes.** Compute the SRI hash against the *decoded* (uncompressed) content, which is what the browser receives after decompression. `response.text()` and `response.arrayBuffer()` return decoded content — do not pass compressed bytes to `crypto.subtle.digest`.

**Multiple `integrity` values require a consistent algorithm set across the page.** If you mix `sha-384` on some tags and `sha-512` on others, browsers apply per-tag algorithm selection. This is valid, but your monitoring tooling must account for multiple valid hashes per resource.

**`require-sri-for script style` CSP directive is experimental.** As of 2026, this directive is supported in Chrome/Edge but not Firefox or Safari. Use it as an additional signal, not as your sole enforcement mechanism.

**SubtleCrypto `digest` returns an `ArrayBuffer`.** The `btoa(String.fromCharCode(...))` pattern works for small assets but may cause a stack overflow for very large buffers (> few MB) because `String.fromCharCode` receives a spread array. For large assets use a chunked approach or `TextDecoder`.

---

## Verification

```bash
# 1. Fetch a rendered HTML page and extract the integrity attribute
curl -s https://app.example.com/ | grep -oP 'integrity="[^"]+"'
# Expected: integrity="sha384-<base64>"

# 2. Independently compute the hash of the same asset
CONTENT=$(curl -s https://cdn.example.com/analytics.js)
echo -n "$CONTENT" | openssl dgst -sha384 -binary | base64
# Must match the value from step 1

# 3. Verify the browser rejects a tampered asset
# Temporarily point the CDN to a modified file; the browser's devtools
# console should show:
# "Failed to find a valid digest in the 'integrity' attribute for resource..."
```

---

## Related

- `subresource-integrity-sri.md` — SRI fundamentals and static HTML usage
- `subresource-integrity-sri-cdn-assets.md` — SRI for assets served from Cloudflare CDN
- `content-security-policy-workers-nonce.md` — CSP nonces for inline scripts
- `api-key-rotation-workers-kv-secrets.md` — KV patterns for per-asset metadata storage

---

## Sources

- W3C Subresource Integrity specification: https://www.w3.org/TR/SRI/
- MDN Web Docs — Subresource Integrity: https://developer.mozilla.org/en-US/docs/Web/Security/Subresource_Integrity
- Web Crypto API — `SubtleCrypto.digest()`: https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/digest
- Cloudflare Workers Runtime APIs — Web Crypto: https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- CSP `require-sri-for` directive: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/require-sri-for
