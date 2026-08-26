# Workers Google Fonts Self-Hosting Proxy — Privacy and Performance

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Pages served from Cloudflare load Google Fonts directly from `fonts.googleapis.com`, leaking visitor IPs to Google and adding a cross-origin DNS round-trip. Routing font stylesheets and font files through a Worker eliminates the third-party origin, satisfies GDPR requirements around data minimisation, and cuts font load time by serving files from Cloudflare's edge cache.

## Context

A Workers proxy rewrites `<link>` stylesheet references so the browser fetches from your own hostname instead of `fonts.googleapis.com`. The Worker fetches the real stylesheet from Google on behalf of the server (not the browser), rewrites all `url(...)` references in the CSS body to point back at itself, then caches the font binary files in the Cache API. This pattern works with any CSS font provider that serves self-contained stylesheet + woff2 URLs. The rewrite must account for the browser's `User-Agent` header so Google returns the most modern font format (woff2).

## CSS Stylesheet Rewriting

```typescript
const FONT_ORIGIN = "https://fonts.googleapis.com";
const FONT_FILE_ORIGIN = "https://fonts.gstatic.com";

export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    // Route: /fonts/css?family=... → proxy Google Fonts CSS
    if (url.pathname === "/fonts/css") {
      return proxyFontStylesheet(url, request.headers.get("User-Agent") ?? "");
    }

    // Route: /fonts/file/* → proxy the actual woff2 binary
    if (url.pathname.startsWith("/fonts/file/")) {
      return proxyFontFile(url.pathname);
    }

    return new Response("Not found", { status: 404 });
  },
};

async function proxyFontStylesheet(
  incomingUrl: URL,
  userAgent: string
): Promise<Response> {
  const upstreamUrl = new URL(`${FONT_ORIGIN}/css2`);
  // Forward all original query params (family=, display=, etc.)
  incomingUrl.searchParams.forEach((v, k) => upstreamUrl.searchParams.set(k, v));

  const cache = caches.default;
  const cacheKey = new Request(upstreamUrl.toString() + "|ua=" + userAgent);

  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  const upstream = await fetch(upstreamUrl.toString(), {
    headers: {
      // Pass the real UA so Google returns woff2 (modern) instead of ttf
      "User-Agent": userAgent,
      Accept: "text/css,*/*;q=0.1",
    },
  });

  if (!upstream.ok) {
    return new Response("Upstream font CSS error", { status: 502 });
  }

  let css = await upstream.text();

  // Rewrite all font file URLs to go through our proxy
  css = css.replace(
    /url\((https:\/\/fonts\.gstatic\.com\/[^)]+)\)/g,
    (_, originalUrl: string) => {
      const encoded = encodeURIComponent(originalUrl);
      return `url(/fonts/file/${encoded})`;
    }
  );

  const response = new Response(css, {
    headers: {
      "Content-Type": "text/css; charset=utf-8",
      // Cache for 24 h at the edge, 1 h in browsers
      "Cache-Control": "public, max-age=3600, s-maxage=86400",
      "Access-Control-Allow-Origin": "*",
    },
  });

  // Store with a short TTL; font families rarely change but family params might
  await cache.put(cacheKey, response.clone());
  return response;
}
```

## Font Binary File Proxy

```typescript
async function proxyFontFile(pathname: string): Promise<Response> {
  // pathname = /fonts/file/<url-encoded-gstatic-url>
  const encoded = pathname.replace("/fonts/file/", "");
  let fontUrl: string;
  try {
    fontUrl = decodeURIComponent(encoded);
  } catch {
    return new Response("Invalid font URL", { status: 400 });
  }

  // Only allow proxying from fonts.gstatic.com
  if (!fontUrl.startsWith(FONT_FILE_ORIGIN)) {
    return new Response("Forbidden origin", { status: 403 });
  }

  const cache = caches.default;
  const cacheKey = new Request(fontUrl);
  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  const upstream = await fetch(fontUrl);
  if (!upstream.ok) {
    return new Response("Upstream font file error", { status: 502 });
  }

  // Font files are immutable (content-addressed URLs), so long TTL is safe
  const response = new Response(upstream.body, {
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "font/woff2",
      "Cache-Control": "public, max-age=31536000, immutable",
      "Access-Control-Allow-Origin": "*",
    },
  });

  await cache.put(cacheKey, response.clone());
  return response;
}
```

## Injecting the Proxy into HTML Responses

```typescript
// Use an HTMLRewriter to rewrite font links in any proxied HTML page
export function rewriteFontLinks(response: Response): Response {
  return new HTMLRewriter()
    .on('link[rel="preconnect"][href*="fonts.googleapis.com"]', {
      element(el) {
        el.remove(); // Remove direct Google Fonts preconnect hints
      },
    })
    .on('link[rel="stylesheet"][href*="fonts.googleapis.com"]', {
      element(el) {
        const href = el.getAttribute("href") ?? "";
        const original = new URL(href);
        // Rewrite to self-hosted proxy
        const proxied =
          "/fonts/css?" + original.searchParams.toString();
        el.setAttribute("href", proxied);
      },
    })
    .transform(response);
}

// Example: wrap an origin fetch in a Worker
export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/fonts/css" || url.pathname.startsWith("/fonts/file/")) {
      // Handled by the font proxy routes above (combine into one Worker)
    }
    const origin = await fetch(request);
    return rewriteFontLinks(origin);
  },
};
```

## Anti-patterns

- Forwarding the visitor's IP to `fonts.googleapis.com` by not stripping forwarding headers — defeats the privacy goal; always use a fresh `fetch()` without the incoming IP headers.
- Caching font CSS without including the `User-Agent` in the cache key — results in modern browsers receiving ttf instead of woff2, bloating transfer size.
- Using a catch-all URL pattern without origin validation — allows SSRF by encoding arbitrary URLs in the `/fonts/file/` path segment.

## Gotchas

- Cloudflare Pages sites can reference Cloudflare Fonts (`/cdn-cgi/fonts/`) natively without a Worker; this article is for Workers-hosted apps or for finer control over font URLs.
- The Google Fonts CSS API v1 (`/css`) is deprecated; always request `/css2` which supports `display=swap` and woff2.

## Verification

```bash
# Check that the stylesheet is served from your Worker, not Google
curl -sI "https://your-worker.example.com/fonts/css?family=Inter:wght@400;700&display=swap" \
  | grep -E "content-type|cache-control|server"

# Confirm no font requests hit fonts.gstatic.com in the browser
# Open DevTools → Network → filter "gstatic" → should be empty

# Verify immutable caching on font files
curl -sI "https://your-worker.example.com/fonts/file/<encoded-url>" \
  | grep cache-control
# Expected: cache-control: public, max-age=31536000, immutable
```

## Related

- `cloudflare/workers-cache-api.md`
- `cloudflare/workers-fetch-api-patterns.md`
- `cloudflare/cloudflare-pages-custom-domain-ssl.md`

## Sources

- https://developers.cloudflare.com/workers/examples/rewrite-links/
- https://developers.cloudflare.com/workers/runtime-apis/cache/
- https://developers.cloudflare.com/speed/fonts/
