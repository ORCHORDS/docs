# Edge-Side Includes with Workers HTMLRewriter

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You need ESI-style fragment composition at the edge without Varnish or a dedicated ESI proxy. A Workers script intercepts the origin HTML, finds `<esi:include >` tags, fetches each fragment URL in parallel, injects the response HTML into the document, and caches each fragment independently. When a fragment fetch fails, a placeholder is injected instead.

---

## Context
Cloudflare Workers' `HTMLRewriter` is a streaming HTML parser that fires handler callbacks as the response body passes through the Worker, without buffering the full document. Each `<esi:include>` element is intercepted by an `ElementHandler`; the fragment URL is extracted, fetched (potentially from the Workers Cache API), and the resolved HTML appended as a child of the tag. Using `Promise.all` for the parallel fragment fetches avoids serial latency amplification. Fragments are cached in a dedicated `Cache` instance keyed on their URL; the TTL is set by the fragment's own `Cache-Control` response header. On fetch failure the handler falls back to a configurable placeholder HTML string.

---

## Section 1 — Worker Entry and Cache Setup

`wrangler.toml`
```toml
name = "esi-rewriter"
main = "src/index.ts"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]

[vars]
ORIGIN_URL = "https://origin.example.com"
FRAGMENT_CACHE_NAME = "esi-fragments-v1"
FRAGMENT_TIMEOUT_MS = "3000"
```

---

## Section 2 — HTMLRewriter ESI Handler

`src/esi-handler.ts`
```typescript
export interface EsiIncludeTag {
  src: string;
  alt?: string; // fallback URL
  placeholder: string; // inline HTML to use when both src and alt fail
}

/**
 * Collects all <esi:include> elements from the document stream.
 * We record them here and resolve their content in a second pass
 * so that all fragment fetches can be parallelised with Promise.all.
 */
export class EsiCollector implements ElementHandler {
  public readonly tags: EsiIncludeTag[] = [];

  element(element: Element): void {
    const src = element.getAttribute('src');
    if (!src) {
      element.remove();
      return;
    }
    this.tags.push({
      src,
      alt: element.getAttribute('alt') ?? undefined,
      placeholder:
        element.getAttribute('placeholder') ??
        '<!-- ESI fragment unavailable -->',
    });
    // Mark with a stable id so the second-pass rewriter can target it
    element.setAttribute('data-esi-id', String(this.tags.length - 1));
  }
}

/**
 * Second-pass handler that injects pre-fetched fragment HTML.
 * fragments: Map<esi-id, html string>
 */
export class EsiInjector implements ElementHandler {
  constructor(private readonly fragments: Map<number, string>) {}

  element(element: Element): void {
    const idStr = element.getAttribute('data-esi-id');
    if (idStr === null) return;
    const html = this.fragments.get(parseInt(idStr, 10)) ?? '';
    element.replace(html, { html: true });
  }
}
```

`src/fragment-fetcher.ts`
```typescript
const CACHE_NAME = (env: Record<string, string>) =>
  env.FRAGMENT_CACHE_NAME ?? 'esi-fragments-v1';

const TIMEOUT_MS = (env: Record<string, string>) =>
  parseInt(env.FRAGMENT_TIMEOUT_MS ?? '3000', 10);

export async function fetchFragment(
  url: string,
  env: Record<string, string>
): Promise<string> {
  const cache = await caches.open(CACHE_NAME(env));
  const cacheKey = new Request(url);

  // 1. Cache hit
  const cached = await cache.match(cacheKey);
  if (cached) return cached.text();

  // 2. Network fetch with timeout
  const controller = new AbortController();
  const timer = setTimeout(
    () => controller.abort(),
    TIMEOUT_MS(env)
  );

  let response: Response;
  try {
    response = await fetch(url, { signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    throw new Error(`Fragment fetch failed: ${response.status} ${url}`);
  }

  // 3. Clone before consuming body — Cache API requires an unconsumed Response
  const [forCache, forReturn] = response.tee();
  // Store only if fragment sends a cacheable Cache-Control
  const cc = response.headers.get('cache-control') ?? '';
  if (!cc.includes('no-store') && !cc.includes('private')) {
    await cache.put(cacheKey, forCache);
  }

  return forReturn.text();
}
```

---

## Section 3 — Worker Entry Point

`src/index.ts`
```typescript
import { EsiCollector, EsiInjector, type EsiIncludeTag } from './esi-handler';
import { fetchFragment } from './fragment-fetcher';

interface Env {
  ORIGIN_URL: string;
  FRAGMENT_CACHE_NAME: string;
  FRAGMENT_TIMEOUT_MS: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const originUrl = new URL(request.url);
    originUrl.hostname = new URL(env.ORIGIN_URL).hostname;
    originUrl.protocol = new URL(env.ORIGIN_URL).protocol;

    // Fetch the origin document
    const originResponse = await fetch(new Request(originUrl.toString(), request));

    // Only process HTML responses
    const contentType = originResponse.headers.get('content-type') ?? '';
    if (!contentType.includes('text/html')) {
      return originResponse;
    }

    // Pass 1: collect all <esi:include> tags
    const collector = new EsiCollector();
    const passOneResponse = new HTMLRewriter()
      .on('esi\\:include', collector)
      .transform(originResponse);

    // Consume the response so the handler fires
    const intermediateHtml = await passOneResponse.text();

    // Fetch all fragments in parallel
    const resolvedFragments = new Map<number, string>();
    await Promise.all(
      collector.tags.map(async (tag: EsiIncludeTag, index: number) => {
        try {
          const html = await fetchFragment(tag.src, env as unknown as Record<string, string>);
          resolvedFragments.set(index, html);
        } catch {
          // Try alt URL if provided
          if (tag.alt) {
            try {
              const html = await fetchFragment(tag.alt, env as unknown as Record<string, string>);
              resolvedFragments.set(index, html);
              return;
            } catch {
              // fall through to placeholder
            }
          }
          resolvedFragments.set(index, tag.placeholder);
        }
      })
    );

    // Pass 2: inject resolved fragments
    const injector = new EsiInjector(resolvedFragments);
    const finalResponse = new HTMLRewriter()
      .on('[data-esi-id]', injector)
      .transform(
        new Response(intermediateHtml, {
          status: originResponse.status,
          headers: originResponse.headers,
        })
      );

    return finalResponse;
  },
};
```

Example origin HTML fragment
```html
<!doctype html>
<html>
  <body>
    <header>
      <esi:include src="https://fragments.example.com/nav" placeholder="<nav>Menu unavailable</nav>" />
    </header>
    <main>
      <h1>Hello</h1>
      <esi:include src="https://fragments.example.com/promo" alt="https://cdn.example.com/promo-fallback.html" />
    </main>
  </body>
</html>
```

---

## Anti-patterns
- **Single-pass replacement** — Replacing element content within the same `ElementHandler` pass that reads `src` is unreliable because `element.setInnerContent()` requires the fetch to complete synchronously in the handler, which is not possible with async `fetch()`; use the two-pass approach above.
- **Caching the assembled document** — Cache fragments individually, not the stitched page; individual fragments have independent TTLs and this avoids cache poisoning across compositions.
- **No timeout on fragment fetches** — A slow fragment will hold the response stream open indefinitely; always use `AbortController` with a deadline.
- **Fetching fragments sequentially** — Serial fetches multiply latency; use `Promise.all` to parallelise.

---

## Gotchas
- `HTMLRewriter` streams the response; calling `.text()` on the transformed response is necessary in Pass 1 to ensure all `element()` handler callbacks have fired before you proceed to fetch fragments.
- The `esi:include` selector must escape the colon for `HTMLRewriter`'s CSS-selector-like syntax: use `'esi\\:include'`.
- `response.tee()` splits the body stream; reading from both clones concurrently is fine but ensure you pass one to `cache.put()` and read the other — do not call `.text()` on the original after `.tee()`.
- Workers Cache API `put()` is eventually consistent within a PoP; a request that arrives milliseconds after a `put()` on a cold PoP may still miss.

---

## Verification
```bash
# Install wrangler
npm install --save-dev wrangler

# Local dev with a mock origin
wrangler dev --local

# Inspect fragment cache behaviour
curl -v http://localhost:8787/ 2>&1 | grep -i 'x-cache\|age'

# Deploy
wrangler deploy

# Confirm ESI tags are gone from the rendered output
curl -s https://esi-rewriter.<account>.workers.dev/ | grep -c 'esi:include'
# Expected output: 0
```

---

## Related
- `react-server-components-cloudflare-pages.md`
- `cloudflare-pages-middleware-auth-redirect.md`

---

## Sources
- Cloudflare HTMLRewriter API — https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- Workers Cache API — https://developers.cloudflare.com/workers/runtime-apis/cache/
- ESI specification (W3C) — https://www.w3.org/TR/esi-lang/
