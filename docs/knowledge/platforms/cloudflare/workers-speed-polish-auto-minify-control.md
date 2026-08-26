# Workers Speed — Controlling Polish and Auto Minify Per-Request

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Cloudflare's Speed features (Polish image compression and Auto Minify for HTML/CSS/JS) are configured globally at the zone level, but specific request paths need different behaviour — e.g. disabling minification for a debug path, or disabling Polish for an API route that returns binary payloads that happen to match image MIME types. Workers can suppress or override these optimizations per-request without touching zone settings.

## Context

Polish converts and compresses images (WebP/AVIF) and strips EXIF metadata. Auto Minify removes whitespace from HTML, CSS, and JS responses. Both features run on Cloudflare's edge after the Worker has completed, but Workers can attach request properties and response headers that instruct the edge to skip or adjust them. The primary mechanisms are `cf` request init properties on subrequests and `Cf-Polished` / cache-control hints on responses. Understanding the execution order (Worker → cache → Polish/Minify → subscriber delivery) is essential.

## Disabling Polish on a Specific Fetch

```typescript
export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    // Raw image API: callers expect the original binary, no conversion
    if (url.pathname.startsWith("/api/raw-image/")) {
      return fetchWithoutPolish(request);
    }

    // Blog images: enable lossy WebP Polish for best compression
    if (url.pathname.startsWith("/blog/images/")) {
      return fetchWithPolish(request, "lossy");
    }

    // Default: pass through with zone-level defaults
    return fetch(request);
  },
};

async function fetchWithoutPolish(request: Request): Promise<Response> {
  const response = await fetch(request, {
    cf: {
      // Disable image compression entirely for this subrequest
      polish: "off",
      // Also disable mirage (mobile image lazy loading)
      mirage: false,
    },
  });
  return response;
}

async function fetchWithPolish(
  request: Request,
  mode: "lossy" | "lossless"
): Promise<Response> {
  return fetch(request, {
    cf: {
      polish: mode,
      // WebP is served when the Accept header includes it
      webp: request.headers.get("Accept")?.includes("image/webp") ?? false,
    },
  });
}
```

## Disabling Auto Minify on Debug Routes

```typescript
export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const isDebugRoute = url.pathname.startsWith("/debug/");

    const response = await fetch(request, {
      cf: {
        // Minification options: can be toggled per-resource-type
        minify: isDebugRoute
          ? { javascript: false, css: false, html: false }
          : { javascript: true, css: true, html: true },
        // Speed Brain (early hints preloading) may also be suppressed
        // by setting cacheEverything: false for API routes
        cacheEverything: !url.pathname.startsWith("/api/"),
      },
    });

    return response;
  },
};
```

## Reading Polish Status from Response Headers

```typescript
// Cloudflare adds Cf-Polished to indicate what was done to an image.
// Useful for debugging or logging compression savings.
export default {
  async fetch(request: Request): Promise<Response> {
    const response = await fetch(request);

    const polishedHeader = response.headers.get("Cf-Polished");
    if (polishedHeader) {
      // Format: "origFmt=jpeg,origSize=84219"
      const parts = Object.fromEntries(
        polishedHeader.split(",").map((kv) => kv.split("=") as [string, string])
      );
      const origSize = parseInt(parts["origSize"] ?? "0", 10);
      const newSize = parseInt(
        response.headers.get("Content-Length") ?? "0",
        10
      );

      if (origSize > 0 && newSize > 0) {
        const savings = (((origSize - newSize) / origSize) * 100).toFixed(1);
        console.log(
          `Polish savings for ${request.url}: ${savings}% ` +
            `(${origSize} → ${newSize} bytes, orig format: ${parts["origFmt"]})`
        );
      }
    }

    return response;
  },
};
```

## Combining Polish, Minify, and Cache Rules

```typescript
interface RoutePolicy {
  polish: "off" | "lossless" | "lossy";
  minify: { javascript: boolean; css: boolean; html: boolean };
  cacheEverything: boolean;
  cacheTtl?: number;
}

function getPolicyForUrl(url: URL): RoutePolicy {
  if (url.pathname.startsWith("/api/")) {
    return {
      polish: "off",
      minify: { javascript: false, css: false, html: false },
      cacheEverything: false,
    };
  }
  if (url.pathname.startsWith("/assets/images/")) {
    return {
      polish: "lossy",
      minify: { javascript: false, css: false, html: false },
      cacheEverything: true,
      cacheTtl: 2592000, // 30 days
    };
  }
  if (url.pathname.startsWith("/assets/")) {
    return {
      polish: "off",
      minify: { javascript: true, css: true, html: false },
      cacheEverything: true,
      cacheTtl: 86400,
    };
  }
  // Default for HTML pages
  return {
    polish: "off",
    minify: { javascript: false, css: false, html: true },
    cacheEverything: false,
  };
}

export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const policy = getPolicyForUrl(url);

    const cfOptions: RequestInitCfProperties = {
      polish: policy.polish,
      minify: policy.minify,
      cacheEverything: policy.cacheEverything,
    };

    if (policy.cacheTtl !== undefined) {
      cfOptions.cacheTtl = policy.cacheTtl;
    }

    return fetch(request, { cf: cfOptions });
  },
};
```

## Anti-patterns

- Setting `cf.polish` on requests to your own Worker's internal subrequests that never return images — it is a no-op but signals a logic error and adds confusion.
- Enabling `cf.minify.html = true` for JSON or binary API responses — the minifier is type-aware, but verifying MIME type before enabling avoids unexpected mutations.
- Relying on `Cf-Polished` being present when the image was already a cached WebP — the header may be absent on cache hits; always treat it as optional.

## Gotchas

- `cf.minify` options require the **Auto Minify** feature to be enabled at the zone level; setting them in Workers does not enable the feature if it is globally off — it only controls per-request overrides.
- Polish does not apply to images served with `Content-Encoding: gzip` or `br`; the Worker must not pre-compress image responses.

## Verification

```bash
# Check Polish was applied (header present on image request)
curl -sI "https://example.com/assets/images/hero.jpg" | grep -i cf-polished

# Confirm minify off for debug route
curl -s "https://example.com/debug/bundle.js" | head -c 200
# Should show original whitespace/comments

# Confirm minify on for assets
curl -s "https://example.com/assets/app.js" | head -c 200
# Should show minified output

# Inspect cf options via Wrangler local dev
wrangler dev --local
```

## Related

- `cloudflare/workers-cache-api.md`
- `cloudflare/client-hints-adaptive-image-delivery-mobile.md`
- `cloudflare/cloudflare-images-transform-urls-variants.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/request/#the-cf-property-requestinitcfproperties
- https://developers.cloudflare.com/speed/optimization/content/auto-minify/
- https://developers.cloudflare.com/images/polish/
