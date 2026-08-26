# View Transitions API with Server-Side Partial Rendering from Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

MPA (multi-page application) navigations cause hard page reloads with jarring visual jumps. You want smooth animated transitions between pages — like a native app — without adopting a full SPA framework, while keeping server-rendered HTML for performance and SEO.

## Context

The View Transitions API (`document.startViewTransition()`) allows the browser to animate between two DOM states. When combined with the Navigation API, you can intercept clicks, fetch only the changed HTML fragment from a Cloudflare Worker, and swap it in — all with a CSS-animated crossfade or slide. The Worker returns lightweight HTML partials rather than full pages, reducing transfer size by 60–90%.

Support: Chrome 111+, Edge 111+. Firefox and Safari require a feature-detection fallback (full navigation).

---

## Solution

### 1. Worker Endpoint — Return HTML Fragment

```typescript
// worker/src/index.ts
import { Hono } from 'hono';

const app = new Hono<{ Bindings: { ASSETS: Fetcher } }>();

/**
 * Detect partial request via custom header set by the client-side script.
 * Returns only the <main> fragment instead of a full HTML document.
 */
app.get('*', async (c) => {
  const isPartial = c.req.header('X-Partial') === '1';

  // Fetch the full page from the static asset binding
  const assetResponse = await c.env.ASSETS.fetch(c.req.raw);

  if (!isPartial) {
    return assetResponse;
  }

  // Parse and extract only the <main> element using HTMLRewriter
  let fragment = '';
  const rewriter = new HTMLRewriter()
    .on('main', {
      element(el) {
        // We want the outer HTML; collect via text chunks
      },
      text(chunk) {
        fragment += chunk.text;
      },
    });

  // Stream the full page through the rewriter but capture the fragment
  // Simpler approach: stream the response and extract via a tagged sentinel
  const fullHtml = await assetResponse.text();
  const mainMatch = fullHtml.match(/<main[^>]*>([\s\S]*?)<\/main>/);
  const mainContent = mainMatch ? mainMatch[0] : '<main><p>Not found</p></main>';

  return new Response(mainContent, {
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
      'Vary': 'X-Partial',
    },
  });
});

export default app;
```

### 2. HTMLRewriter-Based Fragment Extractor

```typescript
// worker/src/fragment.ts

/**
 * Extract a named element's outer HTML from a streaming Response using HTMLRewriter.
 * More memory-efficient than `.text()` for large pages.
 */
export async function extractFragment(
  response: Response,
  selector: string
): Promise<string> {
  const chunks: string[] = [];
  let insideTarget = false;
  let depth = 0;

  const rewriter = new HTMLRewriter()
    .on(selector, {
      element(el) {
        insideTarget = true;
        depth = 1;
        const attrs = [...el.attributes]
          .map(([k, v]) => ` ${k}="${v}"`)
          .join('');
        chunks.push(`<${el.tagName}${attrs}>`);
        el.onEndTag(() => {
          chunks.push(`</${el.tagName}>`);
          insideTarget = false;
        });
      },
      text(chunk) {
        if (insideTarget) chunks.push(chunk.text);
      },
    });

  // Consume the stream — HTMLRewriter buffers internally
  await rewriter.transform(response).text();

  return chunks.join('');
}
```

### 3. Client-Side Navigation Intercept

```typescript
// public/js/transitions.ts

const PARTIAL_HEADER = 'X-Partial';
const MAIN_SELECTOR = 'main';

/**
 * Check View Transitions API support.
 * Falls back to normal navigation if unsupported.
 */
const supportsViewTransitions = 'startViewTransition' in document;

/**
 * Intercept all same-origin navigations via the Navigation API.
 */
if ('navigation' in window) {
  (window as any).navigation.addEventListener(
    'navigate',
    (event: NavigateEvent) => {
      const url = new URL(event.destination.url);

      // Only intercept same-origin GET navigations — not downloads, cross-origin, etc.
      if (
        url.origin !== location.origin ||
        !event.canIntercept ||
        event.hashChange ||
        event.downloadRequest
      ) {
        return;
      }

      event.intercept({
        async handler() {
          await navigateWithTransition(url);
        },
      });
    }
  );
}

async function navigateWithTransition(url: URL): Promise<void> {
  const html = await fetchPartial(url.href);

  if (supportsViewTransitions) {
    await document.startViewTransition(() => swapContent(html)).finished;
  } else {
    swapContent(html);
  }

  // Update the document title if the fragment contains a <title> comment marker
  const titleMatch = html.match(/<!--title:([^-]*)-->/);
  if (titleMatch) document.title = titleMatch[1].trim();

  // Scroll to top on navigation
  window.scrollTo({ top: 0, behavior: 'instant' });
}

async function fetchPartial(href: string): Promise<string> {
  const response = await fetch(href, {
    headers: { [PARTIAL_HEADER]: '1' },
    credentials: 'same-origin',
  });

  if (!response.ok) {
    throw new Error(`Partial fetch failed: ${response.status}`);
  }

  return response.text();
}

function swapContent(html: string): void {
  const main = document.querySelector(MAIN_SELECTOR);
  if (!main) return;

  // Use a template to parse the HTML fragment safely
  const tpl = document.createElement('template');
  tpl.innerHTML = html;
  const newMain = tpl.content.querySelector(MAIN_SELECTOR);

  if (newMain) {
    main.replaceWith(newMain);
  }
}
```

### 4. CSS Transition Animations

```css
/* public/css/transitions.css */

/**
 * Default crossfade for the entire page snapshot.
 * ::view-transition-old — the outgoing screenshot.
 * ::view-transition-new — the incoming screenshot.
 */
::view-transition-old(root) {
  animation: 200ms ease-out fade-out;
}

::view-transition-new(root) {
  animation: 300ms ease-in fade-in;
}

@keyframes fade-out {
  from { opacity: 1; }
  to   { opacity: 0; }
}

@keyframes fade-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}

/**
 * Named transition for hero images — slide from right.
 * Mark the element in HTML: style="view-transition-name: hero-img"
 */
::view-transition-old(hero-img) {
  animation: 250ms ease-in-out slide-out-left;
}

::view-transition-new(hero-img) {
  animation: 250ms ease-in-out slide-in-right;
}

@keyframes slide-out-left {
  to { transform: translateX(-30px); opacity: 0; }
}

@keyframes slide-in-right {
  from { transform: translateX(30px); opacity: 0; }
}

/**
 * Respect reduced-motion preference.
 */
@media (prefers-reduced-motion: reduce) {
  ::view-transition-old(root),
  ::view-transition-new(root) {
    animation-duration: 0.01ms;
  }
}
```

### 5. Worker wrangler.toml

```toml
# wrangler.toml
name = "view-transitions-edge"
main = "worker/src/index.ts"
compatibility_date = "2024-09-23"

[assets]
directory = "./public"
binding = "ASSETS"
```

---

## Implementation Details

- The `X-Partial: 1` request header signals to the Worker that only the `<main>` fragment is needed. This avoids duplicating the layout shell (header, nav, footer) on every navigation.
- `NavigateEvent.intercept()` replaces the default browser navigation, handing control to your handler. The browser still pushes a history entry and updates the URL.
- `document.startViewTransition(callback)` takes a synchronous or async callback that mutates the DOM. The browser captures the before and after screenshots automatically.
- `::view-transition-old` and `::view-transition-new` are pseudo-elements the browser creates in a top-layer. You animate them with standard CSS `@keyframes`.
- Named transitions (`view-transition-name`) allow per-element animations independent of the page crossfade.
- The `Vary: X-Partial` response header ensures CDN/Cloudflare cache correctly keys partials separately from full pages.

---

## Anti-patterns

- **Returning full HTML for partial requests.** This wastes bandwidth and breaks the swap logic since `querySelector('main')` on a `<main>`-only fragment works, but nesting is lost.
- **Forgetting `Vary: X-Partial`.** Cache will serve a partial HTML response to a browser expecting a full page (or vice-versa), causing blank-page bugs.
- **Long transition durations.** Anything above 400 ms feels sluggish. 150–250 ms is the sweet spot.
- **Blocking the handler with heavy async work.** The browser shows a navigation-pending indicator while `handler()` is pending. Fetch should be the only async step.
- **Mutating the DOM outside `startViewTransition`.** Changes made before or after the callback are not captured in the transition snapshot.

---

## Gotchas

- The Navigation API is **not** the same as the legacy `popstate` + `pushState` approach. You cannot use both simultaneously without conflicts.
- `event.intercept` is only available when `event.canIntercept` is `true`. Always check this before calling.
- Cross-origin iframes inside `<main>` can cause the transition to flicker or be skipped by the browser as a security measure.
- Safari (as of 2025) supports View Transitions for same-document transitions but not cross-document. The Navigation API intercept approach covered here is same-document, so Safari support is present once they ship the API (check caniuse.com).
- If JavaScript fails to load (e.g., poor connectivity), users still get standard full-page navigation — graceful degradation is automatic.

---

## Verification

```bash
# Deploy
npx wrangler deploy

# Verify partial response headers
curl -sI -H 'X-Partial: 1' https://your-worker.workers.dev/about \
  | grep -E 'content-type|vary|cache-control'
# Expected:
# content-type: text/html; charset=utf-8
# vary: X-Partial
# cache-control: no-store

# Check fragment size vs full page
curl -s https://your-worker.workers.dev/about | wc -c
curl -s -H 'X-Partial: 1' https://your-worker.workers.dev/about | wc -c
# Partial should be 60-90% smaller
```

In Chrome DevTools:
1. Open the Animations panel (Ctrl+Shift+P > "Show Animations").
2. Navigate between pages — you should see `::view-transition-*` animations captured.
3. Verify the Network panel shows `X-Partial: 1` on navigation XHR requests.

---

## Related

- `documentation/categories/frontend/workers-spa-history-api-routing.md`
- `documentation/categories/frontend/workers-html-minification-htmlrewriter.md`
- `documentation/categories/frontend/htmx-workers-partial-render.md`

---

## Sources

- https://developer.chrome.com/docs/web-platform/view-transitions
- https://developer.mozilla.org/en-US/docs/Web/API/View_Transitions_API
- https://developer.mozilla.org/en-US/docs/Web/API/Navigation_API
- https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- https://caniuse.com/view-transitions
