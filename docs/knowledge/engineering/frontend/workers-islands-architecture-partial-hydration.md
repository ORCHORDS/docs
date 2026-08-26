# Islands Architecture with Partial Hydration via Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You have a content-heavy site (marketing pages, documentation, blog) where most of the UI is static but a handful of interactive regions — a search bar, a comment form, a pricing calculator — need JavaScript. Shipping a full SPA bundle makes the page slow. You need the server to own the static shell while individual interactive "islands" hydrate independently and only when needed.

## Context

Islands architecture (coined by Jason Miller, popularised by Astro and Fresh) treats a page as a sea of static server-rendered HTML with discrete interactive islands floating in it. Cloudflare Workers is an ideal host because:

- It streams HTML from the edge with zero cold-start latency visible to users.
- `HTMLRewriter` can inject island marker attributes on the fly.
- Each island's JS bundle can be loaded from R2 / Workers Assets with aggressive cache headers, independent of the HTML document.
- No Node.js runtime requirement; the Worker runs on V8 isolates.

Partial hydration means only island components call `hydrate()` / `mount()`; the surrounding HTML is never touched by a framework runtime.

## Solution

### 1. Worker: stream the HTML shell and annotate island roots

```typescript
// worker/index.ts
import { Env } from './types';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Fetch the static HTML shell from Workers Assets / R2
    const shellUrl = new URL(request.url);
    shellUrl.hostname = env.ASSETS_HOST; // internal R2 public bucket domain
    const shell = await fetch(shellUrl.toString());

    // Stream through HTMLRewriter, annotating island roots
    return new HTMLRewriter()
      .on('[data-island]', new IslandAnnotator())
      .transform(shell);
  },
};

class IslandAnnotator implements HTMLRewriterElementContentHandlers {
  element(el: Element) {
    const name = el.getAttribute('data-island');
    if (!name) return;
    // Add a unique stable ID so the client can locate the root
    el.setAttribute('data-island-id', crypto.randomUUID());
    // Emit a module-preload link for this island's bundle
    el.before(
      `<link rel="modulepreload" >`,
      { html: true }
    );
  }
}
```

### 2. Static HTML shell (served from R2 / Workers Assets)

```html
<!-- public/index.html -->
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>My Site</title>
  <!-- Island loader bootstrap: tiny, no framework -->
  <script type="module" ></script>
</head>
<body>
  <header>
    <h1>Hello from the edge</h1>
  </header>

  <!-- Static content — zero JS involved -->
  <main>
    <article>...static blog post HTML...</article>
  </main>

  <!-- Interactive island: search -->
  <div data-island="search" data-props='{"placeholder":"Search docs…"}'>
    <!-- Server-rendered fallback shown before hydration -->
    <form action="/search" method="get">
      <input name="q" type="search" placeholder="Search docs…">
      <button type="submit">Go</button>
    </form>
  </div>

  <!-- Interactive island: newsletter -->
  <div data-island="newsletter" data-props='{"listId":"abc123"}'>
    <p>Subscribe to our newsletter</p>
  </div>
</body>
</html>
```

### 3. Island loader — IntersectionObserver-based deferred hydration

```typescript
// public/islands/loader.ts  (compiled to loader.js)

type IslandModule = {
  hydrate(root: HTMLElement, props: unknown): void;
};

const observer = new IntersectionObserver(
  (entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      const el = entry.target as HTMLElement;
      observer.unobserve(el);
      loadIsland(el);
    }
  },
  { rootMargin: '200px' } // start loading 200 px before the island scrolls in
);

// Observe every island root in the document
document.querySelectorAll<HTMLElement>('[data-island]').forEach((el) => {
  observer.observe(el);
});

async function loadIsland(root: HTMLElement): Promise<void> {
  const name = root.dataset.island!;
  const props = JSON.parse(root.dataset.props ?? '{}');

  try {
    // Dynamic import — browser only fetches this when the island nears
    const mod = (await import(`/islands/${name}.js`)) as IslandModule;
    mod.hydrate(root, props);
  } catch (err) {
    console.error(`[islands] failed to load "${name}":`, err);
    // The server-rendered fallback remains functional
  }
}
```

### 4. Example island component (framework-agnostic, Preact shown)

```typescript
// public/islands/search.ts
import { h, render } from 'preact';
import { useState } from 'preact/hooks';

function SearchIsland({ placeholder }: { placeholder: string }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<string[]>([]);

  async function onSubmit(e: Event) {
    e.preventDefault();
    const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
    const data = (await res.json()) as { results: string[] };
    setResults(data.results);
  }

  return h('form', { onSubmit },
    h('input', {
      type: 'search',
      placeholder,
      value: query,
      onInput: (e: InputEvent) => setQuery((e.target as HTMLInputElement).value),
    }),
    h('button', { type: 'submit' }, 'Search'),
    results.length > 0 && h('ul', null,
      results.map((r) => h('li', { key: r }, r))
    )
  );
}

// The contract every island module must satisfy
export function hydrate(root: HTMLElement, props: unknown): void {
  render(h(SearchIsland, props as { placeholder: string }), root);
}
```

### 5. Worker types

```typescript
// worker/types.ts
export interface Env {
  ASSETS_HOST: string; // binding: var in wrangler.toml
  KV: KVNamespace;     // optional: for personalisation later
}
```

### 6. wrangler.toml

```toml
name = "islands-worker"
main = "worker/index.ts"
compatibility_date = "2025-01-01"

[vars]
ASSETS_HOST = "assets.example.workers.dev"

[[rules]]
type = "ESModule"
globs = ["**/*.ts"]
```

## Implementation Details

- **Streaming matters.** `HTMLRewriter` transforms the response in a streaming pipeline; never buffer the whole response. Workers automatically stream `transform()` output to the client as bytes arrive from the origin/R2.
- **modulepreload links** injected by the Worker trigger early fetches so the island bundle is in cache when the IntersectionObserver fires. This eliminates a waterfall: HTML parse → observer fires → fetch bundle.
- **`data-props`** carries server-computed initial state into the island without a separate API call. Keep it small; large payloads belong in a lazy fetch inside the island.
- **Island boundaries must be top-level DOM nodes** — avoid nesting an island inside another island's managed subtree to prevent hydration conflicts.
- **Code-split aggressively.** Each island is its own ES module entry point. A shared `vendor.js` chunk (Preact, etc.) can be loaded once and cached at the edge; use `importmap` to alias it.

## Anti-patterns

- **Loading all island JS eagerly on DOMContentLoaded** defeats the purpose; use IntersectionObserver or user-interaction triggers.
- **Hydrating the full document root** instead of the island root — this causes the framework to own all DOM mutations and removes the static-content benefit.
- **Putting business logic in the loader.** The loader is infrastructure; keep it under 1 KB.
- **Islands that depend on sibling island state** — this coupling belongs in a shared store loaded on demand, not in cross-island DOM queries.
- **Skipping the server-rendered fallback** inside the island root — if JS fails or is blocked, users see an empty box.

## Gotchas

- `crypto.randomUUID()` is available in Workers (Web Crypto standard) but requires the `nodejs_compat` flag only if you import from `node:crypto`. Prefer the global.
- `HTMLRewriter` operates on byte streams; ensure the upstream response has `Content-Type: text/html` or the transformer is a no-op.
- Preload links injected via `el.before()` land *before* the island root in the DOM. If your CSP uses nonces, the Worker must carry the nonce from a `__cf_bm` cookie or generate one per request and inject it into both the CSP header and every `<script>`/`<link>` tag.
- IntersectionObserver `rootMargin` uses viewport-relative units; `200px` is a reasonable pre-load buffer but tune based on island median JS size.

## Verification

1. `wrangler dev` — open DevTools Network panel, confirm island JS bundles are requested only when islands enter (or approach) the viewport.
2. Disable JavaScript in DevTools — confirm the server-rendered fallback inside each island is usable.
3. Run Lighthouse — Time to Interactive and Total Blocking Time should improve vs. a full-bundle SPA.
4. Check `wrangler tail` logs for any `HTMLRewriter` errors on malformed HTML.

## Related

- `workers-edge-personalisation-htmlrewriter.md` — injecting personalised content into the same HTML shell
- `workers-font-subsetting-r2.md` — serving island-specific fonts from R2
- `workers-dark-mode-cookie-edge.md` — edge class injection before streaming

## Sources

- Cloudflare Workers HTMLRewriter docs: https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- Cloudflare Workers Streaming: https://developers.cloudflare.com/workers/examples/transform-response/
- Islands Architecture (Jason Miller): https://jasonformat.com/islands-architecture/
- Astro Islands docs: https://docs.astro.build/en/concepts/islands/
