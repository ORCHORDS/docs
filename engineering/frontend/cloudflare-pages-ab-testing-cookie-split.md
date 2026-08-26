# Cloudflare Pages A/B Testing with Cookie-Based Traffic Split

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

You want to split traffic between two variants of a page (A/B test) at the edge without a third-party experiment platform, without exposing variant assignment to the client until after the HTML lands, and without extra round-trips. Cloudflare Pages Middleware (`functions/_middleware.ts`) intercepts every request before static assets are served, making it the ideal place to assign a sticky variant cookie and rewrite the response path.

---

## Context

Cloudflare Pages static asset serving chooses a file based on the URL path. By placing variant files at predictable paths (`/index.html` vs `/index-b.html`) and using a middleware to rewrite the internal URL based on a cookie, you get:

- Zero client JavaScript needed for assignment
- Sticky assignment (same user always sees same variant)
- No extra round-trip (middleware runs in the same edge request)
- Analytics-friendly (variant stored in cookie, readable by analytics scripts)

Pages Middleware runs as a Cloudflare Worker that wraps `ctx.next()` — the call that fetches the matched static asset. You can short-circuit, rewrite, or augment the response before it reaches the client.

---

## Project Layout

```
/
  public/
    index.html          # Variant A (control)
    index-b.html        # Variant B (treatment)
  functions/
    _middleware.ts      # Traffic-split logic
  wrangler.toml
```

---

## Middleware: Variant Assignment and Path Rewrite

```typescript
// functions/_middleware.ts

const COOKIE_NAME = "ab_variant";
const COOKIE_MAX_AGE = 60 * 60 * 24 * 30; // 30 days
const SPLIT_RATIO = 0.5; // 50 % see variant B

interface Env {
  ASSETS: Fetcher; // automatically bound by Pages
}

export const onRequest: PagesFunction<Env> = async (ctx) => {
  const { request, env, next } = ctx;
  const url = new URL(request.url);

  // Only split on the root path; leave assets and API routes alone
  if (url.pathname !== "/" && url.pathname !== "/index.html") {
    return next();
  }

  // Read existing variant cookie
  const cookieHeader = request.headers.get("Cookie") ?? "";
  let variant = parseCookie(cookieHeader, COOKIE_NAME);

  const isNewAssignment = !variant;
  if (!variant) {
    variant = Math.random() < SPLIT_RATIO ? "b" : "a";
  }

  // Rewrite URL to variant-specific file
  const serveUrl = new URL(request.url);
  if (variant === "b") {
    serveUrl.pathname = "/index-b.html";
  }

  // Fetch the correct static asset
  const assetRequest = new Request(serveUrl.toString(), request);
  const response = await env.ASSETS.fetch(assetRequest);

  // Clone so we can add Set-Cookie header
  const mutableResponse = new Response(response.body, response);

  if (isNewAssignment) {
    mutableResponse.headers.append(
      "Set-Cookie",
      `${COOKIE_NAME}=${variant}; Max-Age=${COOKIE_MAX_AGE}; Path=/; SameSite=Lax; Secure`
    );
  }

  // Expose variant to analytics via a response header
  mutableResponse.headers.set("X-AB-Variant", variant);

  return mutableResponse;
};

function parseCookie(header: string, name: string): string | null {
  const match = header
    .split(";")
    .map((s) => s.trim())
    .find((s) => s.startsWith(`${name}=`));
  return match ? match.slice(name.length + 1) : null;
}
```

---

## Multi-Page Experiments (Route-Scoped Middleware)

For experiments scoped to a sub-path (e.g. `/pricing`), use a route-scoped middleware file instead of the global `_middleware.ts`:

```typescript
// functions/pricing/_middleware.ts

const PRICING_COOKIE = "pricing_variant";

export const onRequest: PagesFunction<Env> = async (ctx) => {
  const cookieHeader = ctx.request.headers.get("Cookie") ?? "";
  let variant = parseCookie(cookieHeader, PRICING_COOKIE);
  const fresh = !variant;
  if (!variant) variant = Math.random() < 0.5 ? "b" : "a";

  const url = new URL(ctx.request.url);
  if (variant === "b") {
    url.pathname = url.pathname.replace("/pricing", "/pricing-b");
  }

  const resp = await ctx.env.ASSETS.fetch(new Request(url.toString(), ctx.request));
  const out = new Response(resp.body, resp);
  if (fresh) {
    out.headers.append(
      "Set-Cookie",
      `${PRICING_COOKIE}=${variant}; Max-Age=2592000; Path=/pricing; SameSite=Lax; Secure`
    );
  }
  return out;
};
```

---

## Reading the Variant in Client Analytics

```typescript
// src/analytics.ts — runs in the browser after page load

function getVariant(): string {
  return (
    document.cookie
      .split(";")
      .map((s) => s.trim())
      .find((s) => s.startsWith("ab_variant="))
      ?.split("=")[1] ?? "a"
  );
}

// Send variant alongside conversion events
function trackConversion(event: string): void {
  const variant = getVariant();
  fetch("/api/analytics", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event, variant, ts: Date.now() }),
  });
}
```

---

## Storing Experiment Results in KV

```typescript
// functions/api/analytics.ts

export const onRequestPost: PagesFunction<Env> = async (ctx) => {
  const { event, variant } = await ctx.request.json<{
    event: string;
    variant: string;
  }>();

  const key = `experiment:homepage:${variant}:${event}`;
  const current = Number(await ctx.env.KV.get(key)) || 0;
  await ctx.env.KV.put(key, String(current + 1));

  return new Response(null, { status: 204 });
};
```

Bind KV in `wrangler.toml`:

```toml
[[kv_namespaces]]
binding = "KV"
id = "YOUR_KV_NAMESPACE_ID"
```

---

## Anti-patterns

- **Splitting on `Math.random()` without stickiness**: Without a cookie or a hashed user ID, the same user gets a different variant on every page load, corrupting your experiment data.
- **Using query parameters for assignment**: Bots and crawlers will index both variants, causing SEO duplication issues. Cookies are invisible to crawlers.
- **Forgetting `Path=/`**: Without a path scope, sub-path pages don't send the cookie, breaking stickiness.
- **Serving two different URLs to the same user**: If variant B changes the `<link rel="canonical">`, both Google and your analytics will treat them as separate pages.
- **Running experiments in client JS after hydration**: This causes layout flash (FOUC) and makes it possible for users to observe the switch. Middleware assignment eliminates this.

---

## Gotchas

- `ctx.env.ASSETS` is automatically bound by Pages — you do not need to declare it in `wrangler.toml` for local or production Pages deployments, but you do need it for `wrangler dev` with `--experimental-local`.
- Cloning a `Response` whose `body` is a `ReadableStream` and then reading from the clone will fail if the original was already consumed. Use `new Response(response.body, response)` immediately after `fetch`.
- The `Set-Cookie` header requires `Secure` in production (Pages always uses HTTPS); omitting it is silently ignored by most browsers on HTTPS but causes confusion in local testing.
- Cloudflare's cache may cache variant A and serve it to variant B users if you don't set `Cache-Control: private` or vary on the cookie. Add `Vary: Cookie` or set `Cache-Control: no-store` on the index response.
- Pages middleware cannot modify the response body of a static asset stream without buffering it first — for body modifications use `HTMLRewriter`.

---

## Verification

```bash
# Assign variant and confirm sticky response
curl -c cookies.txt -s -o /dev/null -w "%{http_code} %header{X-AB-Variant}\n" https://example.pages.dev/
# => 200 a  (or b)

# Second request should return the same variant
curl -b cookies.txt -s -o /dev/null -w "%{http_code} %header{X-AB-Variant}\n" https://example.pages.dev/
# => 200 a  (same)

# Verify cookie in Set-Cookie on first request
curl -v -s https://example.pages.dev/ 2>&1 | grep "Set-Cookie"
# => Set-Cookie: ab_variant=a; Max-Age=2592000; Path=/; SameSite=Lax; Secure
```

---

## Related

- `cloudflare-pages-middleware-auth-gating.md` — middleware composition patterns
- `feature-flags-cloudflare-workers-kv-edge-config.md` — KV-backed feature flags
- `edge-middleware-i18n-routing-cloudflare-pages.md` — other routing use-cases for Pages middleware
- `dark-mode-edge-cookie-cloudflare-pages.md` — cookie-based preferences at the edge

---

## Sources

- Cloudflare Pages — Functions Middleware: https://developers.cloudflare.com/pages/functions/middleware/
- Cloudflare Pages — `ASSETS` binding: https://developers.cloudflare.com/pages/functions/bindings/#assets
- Cloudflare KV — Workers KV API: https://developers.cloudflare.com/kv/api/
- HTTP Cookies spec (RFC 6265): https://datatracker.ietf.org/doc/html/rfc6265
