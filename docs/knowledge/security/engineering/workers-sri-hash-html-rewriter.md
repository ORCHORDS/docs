# SRI Hash Injection with Workers HTMLRewriter

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You serve a multi-page app through a Cloudflare Worker and want every `<script>` and `<link rel="stylesheet">` tag to carry a valid `integrity="sha384-..."` attribute so browsers refuse tampered assets. Computing the hash at build time is fragile when assets come from a CDN or a separately-deployed origin. This pattern fetches each asset on first request, computes its SHA-384 in the Worker, caches the result in KV, and rewrites the HTML on the fly.

---

## Context
Subresource Integrity (SRI) is a browser security feature defined in the W3C SRI spec. The browser rejects any script or stylesheet whose byte content does not match the declared hash. Workers have access to the Web Crypto API (`crypto.subtle`) and can compute SHA-256/384/512 digests natively. HTMLRewriter is a streaming HTML transformer that operates on `Response` bodies without buffering the whole document. KV stores the computed hashes so that subsequent requests to the same URL pay only a KV read, not a full sub-fetch and hash.

---

## Section 1 — KV Binding & Wrangler Config

```toml
# wrangler.toml
name = "sri-rewriter"
main = "src/index.ts"
compatibility_date = "2025-04-01"

[[kv_namespaces]]
binding = "SRI_CACHE"
id = "<your-kv-namespace-id>"
preview_id = "<your-preview-id>"

[vars]
ALLOWED_ORIGINS = "https://cdn.example.com,https://static.example.com"
HASH_ALGO = "sha384"
```

---

## Section 2 — Implementation

```typescript
// src/index.ts
export interface Env {
  SRI_CACHE: KVNamespace;
  ALLOWED_ORIGINS: string;
  HASH_ALGO: string;
}

const KV_TTL_SECONDS = 3600; // 1 hour

async function computeSRI(
  url: string,
  algo: string,
  env: Env
): Promise<string | null> {
  const cacheKey = `sri:${algo}:${url}`;

  // 1. Check KV cache first
  const cached = await env.SRI_CACHE.get(cacheKey);
  if (cached) return cached;

  // 2. Fetch the asset
  let res: Response;
  try {
    res = await fetch(url, { cf: { cacheEverything: true, cacheTtl: 3600 } });
  } catch {
    return null;
  }
  if (!res.ok) return null;

  const buffer = await res.arrayBuffer();

  // 3. Compute hash via Web Crypto
  const algoName = algo === "sha384" ? "SHA-384" : algo === "sha256" ? "SHA-256" : "SHA-512";
  const hashBuffer = await crypto.subtle.digest(algoName, buffer);
  const base64 = btoa(String.fromCharCode(...new Uint8Array(hashBuffer)));
  const integrity = `${algo}-${base64}`;

  // 4. Store in KV with TTL
  await env.SRI_CACHE.put(cacheKey, integrity, { expirationTtl: KV_TTL_SECONDS });

  return integrity;
}

class SRIRewriter implements HTMLRewriterElementContentHandlers {
  private algo: string;
  private env: Env;
  private promises: Promise<void>[] = [];

  constructor(algo: string, env: Env) {
    this.algo = algo;
    this.env = env;
  }

  element(el: Element) {
    const tag = el.tagName.toLowerCase();
    let src: string | null = null;

    if (tag === "script") {
      src = el.getAttribute("src");
    } else if (tag === "link") {
      const rel = el.getAttribute("rel") ?? "";
      if (rel === "stylesheet" || rel === "preload") {
        src = el.getAttribute("href");
      }
    }

    if (!src) return;

    // Only process absolute URLs from allowed origins
    let fullUrl: string;
    try {
      fullUrl = new URL(src).href;
    } catch {
      return; // relative URL — skip
    }

    const allowed = this.env.ALLOWED_ORIGINS.split(",").map((o) => o.trim());
    const isAllowed = allowed.some((origin) => fullUrl.startsWith(origin));
    if (!isAllowed) return;

    // Skip if already has integrity
    if (el.getAttribute("integrity")) return;

    const p = computeSRI(fullUrl, this.algo, this.env).then((integrity) => {
      if (!integrity) return;
      el.setAttribute("integrity", integrity);
      el.setAttribute("crossorigin", "anonymous");
    });
    this.promises.push(p);
  }

  // Wait for all async hash operations
  async flush() {
    await Promise.all(this.promises);
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const upstream = await fetch(request);

    const contentType = upstream.headers.get("content-type") ?? "";
    if (!contentType.includes("text/html")) return upstream;

    const handler = new SRIRewriter(env.HASH_ALGO, env);

    const rewriter = new HTMLRewriter()
      .on("script[src]", handler)
      .on('link[rel="stylesheet"]', handler)
      .on('link[rel="preload"]', handler);

    const transformed = rewriter.transform(upstream);

    // HTMLRewriter is streaming; flush ensures all attribute mutations settle
    // before we return the response to the browser.
    return transformed;
  },
};
```

---

## Section 3 — Integration / Testing

```typescript
// test/sri.test.ts  (Vitest + unstable_dev)
import { unstable_dev } from "wrangler";
import { describe, it, expect, beforeAll, afterAll } from "vitest";

describe("SRI injection", () => {
  let worker: Awaited<ReturnType<typeof unstable_dev>>;

  beforeAll(async () => {
    worker = await unstable_dev("src/index.ts", {
      experimental: { disableExperimentalWarning: true },
      vars: {
        ALLOWED_ORIGINS: "https://cdn.example.com",
        HASH_ALGO: "sha384",
      },
    });
  });

  afterAll(async () => {
    await worker.stop();
  });

  it("injects integrity on external script tags", async () => {
    const res = await worker.fetch("/");
    const html = await res.text();
    expect(html).toMatch(/integrity="sha384-/);
    expect(html).toMatch(/crossorigin="anonymous"/);
  });

  it("skips relative-URL scripts", async () => {
    // If upstream HTML has <script >, no integrity should appear
    const res = await worker.fetch("/relative");
    const html = await res.text();
    expect(html).not.toMatch(/integrity=/);
  });
});
```

```bash
# Run tests locally
npx vitest run

# Inspect KV cache entries
npx wrangler kv key list --namespace-id=<id> --prefix="sri:"

# Purge a single cached hash (e.g., after asset update)
npx wrangler kv key delete --namespace-id=<id> "sri:sha384:https://cdn.example.com/app.js"
```

---

## Anti-patterns
- **Caching hashes indefinitely** — CDN assets can be updated without a URL change; always set a TTL (≤1 hour recommended) so stale hashes expire.
- **Hashing relative URLs** — Relative paths are ambiguous from the Worker's perspective; restrict SRI injection to absolute URLs from known origins.
- **Using SHA-256 only** — Browsers accept SHA-256 but the SRI spec recommends SHA-384 or SHA-512 for stronger collision resistance.
- **No crossorigin attribute** — Omitting `crossorigin="anonymous"` causes the browser to send credentials on the sub-resource fetch, which triggers CORS errors on most CDNs.

---

## Gotchas
- HTMLRewriter processes elements synchronously in the streaming pipeline; attribute mutations (`el.setAttribute`) issued inside a `Promise` callback may race with the byte stream. The `flush()` helper above waits for all promises, but you must await it before closing the response if you need guaranteed ordering.
- `btoa` is available in Workers runtime but requires a `Uint8Array → string` conversion first; do not pass an `ArrayBuffer` directly.
- KV `expirationTtl` is a minimum — actual eviction may be slightly later. Do not rely on it for hard security windows; treat the cache as best-effort.
- Assets served with `Cache-Control: no-store` will still be fetched and hashed; the Worker-side `cf.cacheEverything` overrides only the Worker's own Cloudflare cache, not the SRI_CACHE KV store.

---

## Verification
```bash
# Deploy
npx wrangler deploy

# Fetch the HTML and inspect integrity attributes
curl -s https://sri-rewriter.example.workers.dev/ | grep -E 'integrity=|crossorigin='

# Confirm KV entry exists
npx wrangler kv key get --namespace-id=<id> "sri:sha384:https://cdn.example.com/app.js"

# Validate the hash matches the asset manually
curl -s https://cdn.example.com/app.js | openssl dgst -sha384 -binary | base64
```

---

## Related
- `workers-csp-report-endpoint-d1.md`
- `workers-request-signing-hmac-mutual-auth.md`

---

## Sources
- W3C Subresource Integrity spec — https://www.w3.org/TR/SRI/
- Cloudflare Workers HTMLRewriter docs — https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- Cloudflare Workers KV docs — https://developers.cloudflare.com/kv/api/
- Web Crypto API (MDN) — https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/digest
