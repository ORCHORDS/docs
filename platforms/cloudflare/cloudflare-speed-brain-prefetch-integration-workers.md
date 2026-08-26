# Cloudflare Speed Brain Prefetch Integration with Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You want to eliminate perceived navigation latency by combining Cloudflare's **Speed Brain** (speculation-rules prefetch) with custom Workers logic that controls which URLs are eligible for prefetching, rewrites the injected rule set at the edge, or excludes authenticated/expensive routes from prefetch budgets. Without edge control the browser speculatively fetches pages that require authentication, trigger side effects, or burn KV/D1 quota on cold misses.

---

## Context

Speed Brain injects a `<script type="speculationrules">` block into HTML responses that instructs supporting browsers (Chrome 121+, Edge 121+) to prefetch or prerender `<a>` href targets visible in the viewport. Cloudflare injects this automatically when the feature is enabled in the dashboard (Speed → Optimization → Speed Brain) or via Terraform. Workers sit in the response pipeline and can inspect or rewrite the injected speculation-rules block before it reaches the browser. The key primitives are:

- **HTMLRewriter** — streaming rewriter to intercept the `<script type="speculationrules">` tag.
- **`cf.cacheStatus`** — know whether the page was a cache hit before deciding to allow prefetch.
- **Vary / Cache-Control headers** — gate downstream caching so prefetch responses don't poison authenticated caches.

Speed Brain is distinct from Early Hints (`103`): Early Hints fire on the *current* page's subresources; Speed Brain fires on *future* navigations.

---

## Enabling Speed Brain via Wrangler / API

```typescript
// wrangler.toml — no direct Speed Brain binding; configure via CF API or dashboard.
// Use a Worker to verify injection is occurring and optionally override rules.

// Confirm the feature is active by checking for the injected script in production:
// curl -s https://example.com/ | grep speculationrules
```

---

## Rewriting Speculation Rules in a Worker

Use `HTMLRewriter` to intercept the injected block and replace the URL list with a filtered version derived from your sitemap or allowlist stored in KV.

```typescript
import type { Fetcher } from "@cloudflare/workers-types";

interface Env {
  PREFETCH_ALLOWLIST: KVNamespace;
  ASSETS: Fetcher;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const response = await env.ASSETS.fetch(request);

    // Only process HTML responses on GET requests
    if (
      request.method !== "GET" ||
      !response.headers.get("content-type")?.includes("text/html")
    ) {
      return response;
    }

    // Load the per-site allowlist (array of pathname prefixes)
    const raw = await env.PREFETCH_ALLOWLIST.get("allowlist", "json") as
      | string[]
      | null;
    const allowedPrefixes: string[] = raw ?? ["/blog/", "/docs/", "/pricing"];

    const rewriter = new HTMLRewriter().on(
      'script[type="speculationrules"]',
      {
        element(el) {
          // Remove the Cloudflare-injected block entirely; we'll re-inject ours
          el.remove();
        },
        text() {
          // no-op: element already removed
        },
      }
    );

    // Inject our narrower ruleset into <head>
    const speculationJson = JSON.stringify({
      prefetch: [
        {
          source: "document",
          where: {
            and: allowedPrefixes.map((prefix) => ({
              href_matches: `${prefix}*`,
            })),
          },
          eagerness: "moderate",
        },
      ],
    });

    const headRewriter = new HTMLRewriter().on("head", {
      element(el) {
        el.append(
          `<script type="speculationrules">${speculationJson}</script>`,
          { html: true }
        );
      },
    });

    // Chain transformations: first strip CF block, then inject ours
    const stripped = rewriter.transform(response);
    return headRewriter.transform(stripped);
  },
};
```

---

## Blocking Prefetch for Authenticated or Side-Effect Routes

Some routes must never be prefetched (logout, checkout confirmation, webhook endpoints). Inject a `no-prefetch` meta tag or a `Sec-Purpose: prefetch` header check at the Worker level.

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    const NO_PREFETCH_PATTERNS = [
      /^\/api\//,
      /^\/auth\//,
      /^\/checkout\/confirm/,
      /^\/logout/,
    ];

    const isSideEffect = NO_PREFETCH_PATTERNS.some((re) =>
      re.test(url.pathname)
    );

    // Chrome sends `Sec-Purpose: prefetch` on speculation-rules prefetches
    const isPrefetchRequest =
      request.headers.get("Sec-Purpose") === "prefetch" ||
      request.headers.get("Purpose") === "prefetch";

    if (isSideEffect && isPrefetchRequest) {
      return new Response(null, {
        status: 204,
        headers: {
          "X-Robots-Tag": "noindex",
          "Cache-Control": "no-store",
        },
      });
    }

    return fetch(request);
  },
};
```

---

## Per-Visitor Eagerness Tuning via Cookie

Reduce prefetch eagerness for new visitors (no warm cache) and raise it for repeat visitors with a session cookie.

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const response = await fetch(request);

    if (!response.headers.get("content-type")?.includes("text/html")) {
      return response;
    }

    const isRepeatVisitor = request.headers.get("cookie")?.includes("_session=");
    const eagerness = isRepeatVisitor ? "eager" : "conservative";

    return new HTMLRewriter()
      .on('script[type="speculationrules"]', {
        text(chunk) {
          // Patch eagerness value inline
          if (chunk.text.includes('"eagerness"')) {
            chunk.replace(
              chunk.text.replace(
                /"eagerness":\s*"\w+"/,
                `"eagerness": "${eagerness}"`
              )
            );
          }
        },
      })
      .transform(response);
  },
};
```

---

## Preventing Cache Poisoning on Prefetched Responses

Workers must ensure prefetched responses never cache authenticated content under a shared cache key.

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const response = await fetch(request);
    const headers = new Headers(response.headers);

    const isPrefetch =
      request.headers.get("Sec-Purpose") === "prefetch";

    if (isPrefetch) {
      // Force private caching on prefetch responses carrying auth cookies
      if (request.headers.has("cookie")) {
        headers.set("Cache-Control", "private, no-store");
        headers.set("Vary", "Cookie");
      }
    }

    return new Response(response.body, { status: response.status, headers });
  },
};
```

---

## Anti-patterns

- **Prefetching all hrefs unconditionally**: burns origin quota and triggers rate-limiting on every page load. Use `source: "document"` with `where` filters, not `source: "list"` with `"*"`.
- **Not checking `Sec-Purpose: prefetch`**: side-effect routes (cart add, email unsubscribe) silently execute on hover if not guarded.
- **Chaining HTMLRewriter transforms on the same script tag without removing first**: produces duplicate `<script type="speculationrules">` blocks which Chrome merges but causes confusion in analysis tools.
- **Hardcoding the speculation-rules JSON in the Worker bundle**: the list goes stale; store it in KV with a TTL and refresh asynchronously.

---

## Gotchas

- Speed Brain injection happens *after* the Worker response is committed on the Cloudflare network, unless your Worker intercepts the origin response. If you use a pass-through Worker that calls `fetch(request)` and returns the response directly, Cloudflare still injects the script *after* your Worker — use `HTMLRewriter` to detect this.
- `prerender` eagerness in speculation rules is Chromium-only and consumes significantly more memory. Keep it to `"conservative"` or `"moderate"` for public pages.
- Workers deployed as **Smart Placement** targets may run far from the browser; the round-trip for the Worker-modified HTML response may negate prefetch gains. Disable Smart Placement for front-door Workers that serve HTML.
- Safari and Firefox ignore speculation rules entirely as of 2026. Speed Brain provides no benefit on those browsers; ensure your Worker fallback (normal cache, Early Hints) is still in place.

---

## Verification

```bash
# Confirm Speed Brain is injecting speculation rules
curl -s https://example.com/ | grep -A 10 'speculationrules'

# Confirm prefetch requests are blocked for side-effect routes
curl -H 'Sec-Purpose: prefetch' https://example.com/api/cart -v 2>&1 | grep "< HTTP"

# Inspect cache behavior on prefetch responses
curl -H 'Sec-Purpose: prefetch' -H 'Cookie: _session=abc' \
  https://example.com/dashboard -v 2>&1 | grep -i "cache-control"

# Chrome DevTools → Network → filter "Sec-Purpose: prefetch" to confirm eagerness
```

---

## Related

- `early-hints-speed-brain-browser-support-disparity.md`
- `workers-speed-polish-auto-minify-control.md`
- `workers-cache-api.md`
- `kv-best-practices.md`

---

## Sources

- https://developers.cloudflare.com/speed/optimization/content/speed-brain/
- https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- https://wicg.github.io/nav-speculation/speculation-rules.html
- https://developer.chrome.com/docs/web-platform/prerender-pages
