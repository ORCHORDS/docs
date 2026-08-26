# CSS Anchor Positioning with Edge-Side Feature Detection via Cloudflare Workers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

CSS Anchor Positioning (`anchor()`, `position-anchor`) is supported in Chrome 125+ and Safari 18.2+ but
absent in Firefox and older browsers. Serving the polyfill unconditionally to all users wastes bandwidth
for supported browsers. A Cloudflare Worker can inspect the `User-Agent` or negotiate via `Accept-CH`
to serve the polyfill only when necessary and cache the two variants separately at the edge.

## Context

CSS Anchor Positioning lets an element declare itself as an anchor via `anchor-name` and a second element
position itself relative to that anchor with `position-anchor` and `anchor()` functions — enabling robust
tooltips, context menus, and popovers without JavaScript layout calculations. The
`@csstools/css-anchor-positioning` polyfill provides a JavaScript fallback, but adds ~25 kB to the
initial load. Cloudflare Workers intercept each request before it reaches the origin, making them ideal
for UA-based branching with Vary-aware caching so CDN cache keys remain separated by support tier.

## Detecting Anchor Positioning Support in a Worker

Parse the `User-Agent` header to determine whether the browser engine supports CSS Anchor Positioning
natively. Use a minimal version-range check — avoid pulling in a full UA parser library to keep the
Worker bundle small.

```typescript
// src/feature-detect.ts
export interface FeatureSupport {
  cssAnchorPositioning: boolean;
}

const ANCHOR_SUPPORT_REGEX: Record<string, number> = {
  'Chrome/':  125,
  'Chromium/': 125,
  'EdgA/':    125,   // Edge Android
  'Edg/':     125,   // Edge desktop
  'Safari/':  18,    // checked alongside Version/
};

/**
 * Returns true if the UA string indicates native CSS Anchor Positioning support.
 * Falls back to false (serve polyfill) when UA is absent or unrecognised.
 */
export function detectCssAnchorPositioning(ua: string): boolean {
  for (const [token, minMajor] of Object.entries(ANCHOR_SUPPORT_REGEX)) {
    const idx = ua.indexOf(token);
    if (idx === -1) continue;

    const versionStr = ua.slice(idx + token.length);
    const major = parseInt(versionStr, 10);
    if (!Number.isFinite(major)) continue;

    // Safari: also require Version/18+ to avoid AppleWebKit/600 false positives
    if (token === 'Safari/') {
      const versionMatch = ua.match(/Version\/(\d+)/);
      if (!versionMatch) return false;
      return parseInt(versionMatch[1], 10) >= 18;
    }

    return major >= minMajor;
  }
  return false; // unknown UA → serve polyfill for safety
}
```

## Serving the Polyfill Conditionally and Setting Cache Keys

The Worker intercepts requests for the main HTML document, sets the `Vary: User-Agent` header so
Cloudflare's CDN maintains separate cache entries per support tier, and injects a `<script>` tag only
for browsers that need the polyfill.

```typescript
// src/index.ts
import { detectCssAnchorPositioning } from './feature-detect';

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // Passthrough for non-HTML assets
    if (!url.pathname.endsWith('/') && url.pathname.includes('.')) {
      return fetch(request);
    }

    const ua = request.headers.get('User-Agent') ?? '';
    const supportsAnchor = detectCssAnchorPositioning(ua);

    // Build a normalised cache key so we only have 2 variants (supported / polyfilled)
    const cacheKey = new Request(
      `${url.href}#anchor=${supportsAnchor ? 'native' : 'polyfill'}`,
      request
    );
    const cache = caches.default;
    const cached = await cache.match(cacheKey);
    if (cached) return cached;

    // Fetch the origin document
    const originResponse = await fetch(request);
    const contentType = originResponse.headers.get('Content-Type') ?? '';
    if (!contentType.includes('text/html')) return originResponse;

    // Inject polyfill script tag when needed
    let html = await originResponse.text();
    if (!supportsAnchor) {
      html = html.replace(
        '</head>',
        `<script type="module" ></script></head>`
      );
    }

    const response = new Response(html, {
      status: originResponse.status,
      headers: {
        ...Object.fromEntries(originResponse.headers),
        'Content-Type': 'text/html; charset=utf-8',
        'Vary': 'User-Agent',
        'Cache-Control': 'public, max-age=300, s-maxage=3600',
        'X-Anchor-Polyfill': supportsAnchor ? 'native' : 'injected',
      },
    });

    ctx.waitUntil(cache.put(cacheKey, response.clone()));
    return response;
  },
} satisfies ExportedHandler<Env>;
```

## CSS Anchor Positioning for Tooltips and Popovers

Once the polyfill is in place for older browsers, author Anchor Positioning CSS normally. The pattern
below positions a tooltip above its trigger button using `anchor()` without JavaScript.

```css
/* styles/anchor-tooltip.css */

/* 1. Declare the anchor on the trigger element */
.tooltip-trigger {
  anchor-name: --tooltip-anchor;
}

/* 2. Position the tooltip relative to the anchor */
.tooltip {
  position: absolute;
  position-anchor: --tooltip-anchor;

  /* Sit above the anchor, centred horizontally */
  bottom: calc(anchor(top) + 0.5rem);
  left: anchor(center);
  translate: -50% 0;

  /* Fallback: if there is no room above, flip below */
  position-try-fallbacks: flip-block;

  /* Prevent the tooltip from leaving the viewport */
  overflow: clip;
  inline-size: max-content;
  max-inline-size: 20rem;
}

/* 3. Tie tooltip visibility to the popover API for accessibility */
.tooltip:popover-open {
  display: block;
}
```

```html
<!-- Matching HTML — no JS layout code needed -->
<button
  class="tooltip-trigger"
  popovertarget="tip-1"
  popovertargetaction="toggle"
  type="button"
>
  Hover / Focus me
</button>

<div id="tip-1" class="tooltip" popover="auto" role="tooltip">
  This tooltip is positioned with CSS Anchor Positioning.
</div>
```

## Differentiating Cache by Feature Support

When the CDN must keep two variants of a cached resource, `Vary: User-Agent` alone would create
thousands of cache keys. Instead, use a normalised cache key suffix and a `Cf-Cache-Tag` so you can
purge both variants at once.

```typescript
// Append to the fetch handler — tag both variants for targeted purge
const CACHE_TAG_BASE = 'anchor-polyfill-tier';

response.headers.append(
  'Cache-Tag',
  `${CACHE_TAG_BASE},${CACHE_TAG_BASE}:${supportsAnchor ? 'native' : 'polyfill'}`
);

// Purge all anchor-polyfill cached responses when polyfill version changes:
// POST https://api.cloudflare.com/client/v4/zones/{zone_id}/purge_cache
// body: { "tags": ["anchor-polyfill-tier"] }
```

## Anti-patterns

- Using `Vary: User-Agent` on the origin without normalisation — creates unbounded cache fragmentation
  across thousands of distinct UA strings.
- Importing a full UA-parser library (ua-parser-js, bowser) into the Worker — bloats the bundle and
  increases cold-start latency; a targeted regex check is sufficient.
- Injecting the polyfill via a client-side `<script>` that feature-detects at runtime — causes a
  flash of unstyled content before the polyfill loads and runs.

## Gotchas

- Cloudflare's CDN respects `Vary` headers but only on responses with cacheable status codes; ensure
  origin returns `Cache-Control: public` or the Worker sets it explicitly.
- The `@csstools/css-anchor-positioning` polyfill must be initialised after the CSS is parsed; load it
  as `type="module"` to guarantee deferred execution after the stylesheet is applied.
- `position-try-fallbacks` requires both the `anchor()` and `@position-try` block — older polyfill
  versions (< 3.0) do not support `position-try-fallbacks` shorthand; pin to ≥ 3.0.

## Verification

```bash
# Start local Worker dev server
wrangler dev --port 8787

# Simulate a supported browser — should see X-Anchor-Polyfill: native
curl -s -I http://localhost:8787/ \
  -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36'

# Simulate Firefox (no native support) — should see X-Anchor-Polyfill: injected
curl -s http://localhost:8787/ \
  -H 'User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0' \
  | grep css-anchor-positioning

# Run Worker unit tests
npx vitest run src/feature-detect.test.ts
```

## Related

- `frontend/css-anchor-positioning-overflow-fallbacks.md`
- `frontend/dark-mode-edge-cookie-cloudflare-pages.md`
- `frontend/feature-flags-cloudflare-workers-kv-edge-config.md`

## Sources

- https://developers.cloudflare.com/workers/examples/cache-using-fetch/
- https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_anchor_positioning
- https://css-tricks.com/css-anchor-positioning-guide/
- https://github.com/csstools/css-anchor-positioning
- https://developers.cloudflare.com/cache/how-to/purge-cache/purge-cache-tags/
