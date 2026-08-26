# Lazy Image Loading Strategy with Workers-Injected Native Attributes

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

HTML pages served through a Worker contain dozens of `<img>` tags without `loading`,
`decoding`, or `fetchpriority` attributes. The browser eagerly fetches all images on
page load, competing with critical CSS and scripts for bandwidth and delaying LCP.
Adding these attributes to every template is tedious and error-prone. A Worker with
`HTMLRewriter` can inject them automatically on every response.

---

## Context

Browser-native lazy loading (`loading="lazy"`) defers off-screen image fetches until
the image is near the viewport. It is supported in all modern browsers (Chrome 76+,
Firefox 75+, Safari 15.4+) and requires zero JavaScript. Combined with
`decoding="async"`, the browser can decode images off the main thread, reducing jank.

`fetchpriority="high"` on the LCP image (hero, above-the-fold banner) tells the browser
to prioritize its fetch over lower-priority resources, improving LCP scores.

Cloudflare's `HTMLRewriter` is a streaming HTML transformer built into the Workers
runtime. It processes the response body as it streams from the origin, injecting
attributes without buffering the full HTML in memory.

**LCP detection heuristic**: The first `<img>` in the document body with a prominent
`class` (hero, banner, lcp, above-fold) or that appears before a known fold marker
(`<main>`, first `<section>`) is treated as the LCP candidate.

---

## Solution

### 1. Basic HTMLRewriter image attribute injector

```typescript
interface Env {
  IMAGES_BUCKET: R2Bucket;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Only rewrite HTML responses
    const response = await fetch(request);
    const contentType = response.headers.get('Content-Type') ?? '';
    if (!contentType.includes('text/html')) return response;

    return new HTMLRewriter()
      .on('img', new ImageAttributeHandler())
      .transform(response);
  },
};
```

### 2. ImageAttributeHandler — lazy load + eager LCP

```typescript
const LCP_CLASSES = new Set(['hero', 'lcp', 'banner', 'above-fold', 'featured']);
const LAZY_CLASSES = new Set(['gallery', 'thumbnail', 'card-img', 'product-img']);

class ImageAttributeHandler implements HTMLRewriterElementContentHandlers {
  private imageIndex = 0;
  private lcpAssigned = false;

  element(el: Element) {
    this.imageIndex++;
    const classList = (el.getAttribute('class') ?? '').split(/\s+/);
    const src = el.getAttribute('src') ?? '';

    // Skip SVG data URIs and tracking pixels
    if (src.startsWith('data:') || src.includes('1x1')) return;

    // Skip images that already have explicit loading attribute
    if (el.getAttribute('loading')) {
      this.maybeMarkLCP(el, classList);
      return;
    }

    const isAboveFold = this.isAboveFold(classList);
    const isBelowFold = this.isBelowFold(classList);

    if (isAboveFold && !this.lcpAssigned) {
      // Mark as LCP candidate
      el.setAttribute('loading', 'eager');
      el.setAttribute('fetchpriority', 'high');
      el.setAttribute('decoding', 'sync'); // LCP: sync decode to avoid delay
      this.lcpAssigned = true;
    } else if (isBelowFold || this.imageIndex > 2) {
      // Lazy-load below-fold or non-first images
      el.setAttribute('loading', 'lazy');
      el.setAttribute('decoding', 'async');
      el.removeAttribute('fetchpriority');
    } else if (this.imageIndex === 1 && !this.lcpAssigned) {
      // First image with no explicit class — treat as potential LCP
      el.setAttribute('loading', 'eager');
      el.setAttribute('fetchpriority', 'high');
      el.setAttribute('decoding', 'sync');
      this.lcpAssigned = true;
    } else {
      el.setAttribute('loading', 'lazy');
      el.setAttribute('decoding', 'async');
    }

    // Always add width/height if missing to avoid layout shifts
    this.addDimensionsHint(el);
  }

  private isAboveFold(classList: string[]): boolean {
    return classList.some((c) => LCP_CLASSES.has(c));
  }

  private isBelowFold(classList: string[]): boolean {
    return classList.some((c) => LAZY_CLASSES.has(c));
  }

  private maybeMarkLCP(el: Element, classList: string[]) {
    if (!this.lcpAssigned && this.isAboveFold(classList)) {
      el.setAttribute('fetchpriority', 'high');
      this.lcpAssigned = true;
    }
  }

  private addDimensionsHint(el: Element) {
    // Only add aspect-ratio hint via style if both dimensions absent
    if (!el.getAttribute('width') && !el.getAttribute('height')) {
      const existingStyle = el.getAttribute('style') ?? '';
      if (!existingStyle.includes('aspect-ratio')) {
        el.setAttribute('style', `${existingStyle} aspect-ratio: 16/9;`.trim());
      }
    }
  }
}
```

### 3. R2 image serving with Cache-Control

```typescript
async function serveImage(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const key = url.pathname.slice(1); // Remove leading /

  const object = await env.IMAGES_BUCKET.get(key, {
    onlyIf: request.headers,
  });

  if (!object) return new Response('Not found', { status: 404 });

  // Conditional request support
  if (object instanceof Response) return object; // 304 Not Modified

  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set('ETag', object.httpEtag);

  // Long cache for content-hashed images, short for non-hashed
  const isHashed = /[a-f0-9]{8,}/.test(key);
  headers.set(
    'Cache-Control',
    isHashed
      ? 'public, max-age=31536000, immutable'
      : 'public, max-age=86400, stale-while-revalidate=3600',
  );
  headers.set('Vary', 'Accept');

  // Return WebP if supported
  const accept = request.headers.get('Accept') ?? '';
  if (accept.includes('image/webp') && object.httpMetadata?.contentType === 'image/jpeg') {
    headers.set('Content-Type', 'image/webp');
  }

  return new Response(object.body, { headers });
}
```

### 4. Responsive srcset injection

```typescript
class SrcsetInjector implements HTMLRewriterElementContentHandlers {
  private readonly baseUrl: string;
  private readonly widths = [320, 640, 960, 1280, 1920];

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  element(el: Element) {
    const src = el.getAttribute('src');
    if (!src || src.startsWith('data:') || el.getAttribute('srcset')) return;

    // Only for R2-served images
    if (!src.startsWith('/images/')) return;

    const baseName = src.replace('/images/', '').replace(/\.[^.]+$/, '');
    const ext = src.match(/\.([^.]+)$/)?.[1] ?? 'jpg';

    const srcset = this.widths
      .map((w) => `/images/${baseName}-${w}w.${ext} ${w}w`)
      .join(', ');

    el.setAttribute('srcset', srcset);
    el.setAttribute(
      'sizes',
      '(max-width: 640px) 100vw, (max-width: 960px) 50vw, 33vw',
    );
  }
}

// Combine both rewriters
function buildRewriter(): HTMLRewriter {
  return new HTMLRewriter()
    .on('img', new ImageAttributeHandler())
    .on('img', new SrcsetInjector('https://images.example.com'));
}
```

### 5. Native lazy load browser support check (client-side)

```typescript
// Inline script to polyfill loading="lazy" for older browsers
const lazySupportSnippet = `
<script>
  if (!('loading' in HTMLImageElement.prototype)) {
    // Fallback: IntersectionObserver-based lazy load
    const images = document.querySelectorAll('img[loading="lazy"]');
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) {
          const img = e.target;
          img.src = img.dataset.src || img.src;
          observer.unobserve(img);
        }
      });
    }, { rootMargin: '200px' });
    images.forEach((img) => observer.observe(img));
  }
</script>
`;

// Inject the snippet before </body>
class ScriptInjector implements HTMLRewriterElementContentHandlers {
  element(el: Element) {
    el.prepend(lazySupportSnippet, { html: true });
  }
}
```

---

## Implementation Details

- **`HTMLRewriter` streaming**: The rewriter processes the response as a stream. Image
  handlers are called in document order. The `imageIndex` counter in the handler class
  is maintained across calls within one response.
- **`onlyIf` conditional fetch from R2**: Passing `request.headers` enables ETag-based
  conditional GETs, returning 304 when the browser has a cached copy.
- **`aspect-ratio` via style**: Injecting an `aspect-ratio` style prevents Cumulative
  Layout Shift (CLS) when image dimensions are not known at parse time.
- **`fetchpriority` browser support**: Chrome 101+, Firefox not yet (2024). Safe to
  add — ignored by unsupported browsers.

---

## Anti-patterns

- **Lazy-loading the LCP image**: The single largest mistake. If the above-fold hero has
  `loading="lazy"`, LCP is delayed until the image enters the viewport — but it was
  always in the viewport.
- **`decoding="sync"` on below-fold images**: Forces synchronous decode on the main
  thread, causing layout jank. Use `async` for everything except the LCP image.
- **Missing width/height attributes**: Without dimensions, the browser cannot reserve
  layout space, causing CLS when images load.
- **Injecting srcset for external images**: Only inject srcset for images you control
  (R2, your CDN). External image srcsets may reference nonexistent variants.

---

## Gotchas

- `HTMLRewriter` handlers cannot read earlier elements in the document (no DOM lookups).
  The LCP heuristic must be stateless and ordered (class-based, index-based).
- If the origin gzip-encodes HTML, the Worker receives compressed bytes. Cloudflare
  decompresses before passing to `HTMLRewriter`. Ensure the response `Content-Encoding`
  header is stripped or updated if you re-encode.
- `loading="lazy"` does not work for images in `<picture>` `<source>` elements — set
  it on the `<img>` tag inside the `<picture>`.
- Safari 15.4 added native lazy load support. Safari 15.3 and below ignore the
  attribute. The IntersectionObserver fallback handles these.

---

## Verification

```bash
# Check injected attributes in the response
curl -s https://your-worker.example.com/ | grep -E 'loading=|decoding=|fetchpriority='

# Expected (first img):
# <img  loading="eager" fetchpriority="high" decoding="sync" ...>
# Subsequent imgs:
# <img  loading="lazy" decoding="async" ...>
```

Measure LCP in Lighthouse:
```bash
npx lighthouse https://your-worker.example.com/ \
  --only-audits=largest-contentful-paint \
  --output json | jq '.audits["largest-contentful-paint"].displayValue'
```

---

## Related

- `workers-early-hints-103-preload.md`
- `lazy-load-images-r2-srcset.md`
- `workers-critical-css-inline-html-rewriter.md`
- `workers-json-streaming-parse-r2.md`

---

## Sources

- MDN loading attribute — https://developer.mozilla.org/en-US/docs/Web/HTML/Element/img#loading
- MDN fetchpriority — https://developer.mozilla.org/en-US/docs/Web/HTML/Element/img#fetchpriority
- Cloudflare HTMLRewriter — https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- web.dev Lazy Loading Images — https://web.dev/articles/lazy-loading-images
- Cloudflare R2 Workers API — https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
