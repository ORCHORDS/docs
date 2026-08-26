# View Transitions API on Cloudflare Pages

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your multi-page application (MPA) deployed on Cloudflare Pages has jarring full-page reloads between routes. You want SPA-like animated transitions without switching to a client-side router, but the View Transitions API is not yet supported in all browsers. You also find that aggressive CDN caching causes a brief flash of stale content when a transition fetches the next page.

## Context

The View Transitions API (`document.startViewTransition()`) lets browsers capture the current DOM state, navigate or mutate the DOM, and animate between the two snapshots using CSS. In an MPA, the browser handles cross-document transitions natively when both pages opt-in via the `@view-transition` CSS at-rule (Chrome 126+). For older browsers the page loads normally without animation. Cloudflare Pages serves assets from its global CDN; setting correct `Cache-Control` headers via a `_headers` file ensures the browser fetches a fresh copy of the destination page during the transition instead of reading a stale entry from the HTTP cache.

## CSS Opt-In and Basic Animation

```css
/* src/styles/transitions.css */

/* Opt both the outgoing and incoming document into cross-document transitions */
@view-transition {
  navigation: auto;
}

/* Default fade — overridden per-element below */
::view-transition-old(root) {
  animation: 200ms ease-in both fade-out;
}
::view-transition-new(root) {
  animation: 300ms ease-out both fade-in;
}

@keyframes fade-out {
  to { opacity: 0; }
}
@keyframes fade-in {
  from { opacity: 0; }
}

/* Named transition for the page heading */
.page-title {
  view-transition-name: page-title;
}
::view-transition-old(page-title) {
  animation: 200ms ease-in both slide-out-up;
}
::view-transition-new(page-title) {
  animation: 300ms ease-out both slide-in-up;
}

@keyframes slide-out-up {
  to { transform: translateY(-24px); opacity: 0; }
}
@keyframes slide-in-up {
  from { transform: translateY(24px); opacity: 0; }
}

/* Respect prefers-reduced-motion */
@media (prefers-reduced-motion: reduce) {
  ::view-transition-old(*),
  ::view-transition-new(*) {
    animation: none;
  }
}
```

## Programmatic Transition with Async Data Fetch

For same-document updates (e.g., filtering a list without navigation), wrap the DOM mutation in `startViewTransition`:

```typescript
// src/scripts/filter.ts
async function applyFilter(category: string): Promise<void> {
  if (!document.startViewTransition) {
    // Graceful fallback — update DOM directly
    await updateList(category);
    return;
  }

  const transition = document.startViewTransition(async () => {
    await updateList(category);
  });

  try {
    await transition.finished;
  } catch (err) {
    // Transition skipped (e.g., user navigated away) — safe to ignore
    if ((err as Error).name !== 'AbortError') throw err;
  }
}

async function updateList(category: string): Promise<void> {
  const res = await fetch(`/api/posts?category=${encodeURIComponent(category)}`);
  if (!res.ok) throw new Error(`Fetch failed: ${res.status}`);
  const posts = await res.json() as Array<{ id: number; title: string }>;

  const list = document.getElementById('post-list')!;
  list.innerHTML = posts
    .map((p) => `<li data-id="${p.id}">${p.title}</li>`)
    .join('');
}

// Attach to filter buttons
document.querySelectorAll<HTMLButtonElement>('[data-filter]').forEach((btn) => {
  btn.addEventListener('click', () => applyFilter(btn.dataset.filter!));
});
```

## Cloudflare Pages `_headers` for Cache-Control

Place this file at the project root (it is deployed alongside your `dist/` output):

```
# public/_headers

# HTML pages — must revalidate so transitions never flash stale content
/*.html
  Cache-Control: public, max-age=0, must-revalidate

/
  Cache-Control: public, max-age=0, must-revalidate

# Hashed JS/CSS assets — immutable, long TTL
/assets/*
  Cache-Control: public, max-age=31536000, immutable

# API routes forwarded to Workers — no CDN caching
/api/*
  Cache-Control: no-store
```

With `max-age=0, must-revalidate` on HTML, Cloudflare's edge and the browser cache will revalidate on every navigation. When the content is unchanged the server returns `304 Not Modified`, keeping the transition fast while guaranteeing freshness.

## Graceful Fallback for Unsupported Browsers

```typescript
// src/scripts/transition-polyfill.ts

/**
 * Intercept same-origin link clicks and use startViewTransition
 * when available; fall through to normal navigation otherwise.
 */
function enhanceLinks(): void {
  if (!('startViewTransition' in document)) return;

  document.addEventListener('click', (e) => {
    const anchor = (e.target as Element).closest<HTMLAnchorElement>('a[href]');
    if (!anchor) return;

    const url = new URL(anchor.href, location.href);
    if (url.origin !== location.origin) return;
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;

    e.preventDefault();
    document.startViewTransition(() => {
      location.href = url.href;
    });
  });
}

document.addEventListener('DOMContentLoaded', enhanceLinks);
```

Browsers without `startViewTransition` simply navigate normally; the CSS `@view-transition` rule is silently ignored by those engines.

## Anti-patterns

- **Setting `view-transition-name` on multiple elements simultaneously** — each name must be unique in the DOM at the time the transition snapshot is taken; duplicates cause the transition to abort.
- **Long-running async work inside `startViewTransition`** — the callback must resolve quickly; heavy data fetching should happen before calling `startViewTransition`, with results captured in a closure.
- **Caching HTML with a long `max-age`** — the browser will show the old page's snapshot transitioning to a cached (stale) new page, breaking the visual intent of the animation.
- **Forgetting `prefers-reduced-motion`** — omitting the media query can cause nausea for users with vestibular disorders; always null-out animations under that preference.

## Gotchas

- Cross-document transitions require `@view-transition { navigation: auto; }` in **both** the outgoing and incoming page's CSS; missing it on either side disables the transition.
- `document.startViewTransition` is only defined in Chrome 111+ and Edge 111+; Safari and Firefox require a feature detect (`'startViewTransition' in document`).
- Cloudflare Pages `_headers` uses exact path matching, not glob for directories; `/articles` does not match `/articles/my-post` — use `/articles/*` explicitly.
- Named `view-transition-name` values must be valid CSS identifiers; strings with spaces or special characters will silently disable the named transition.

## Verification

```bash
# Check Cache-Control headers are applied by Pages
curl -I https://your-project.pages.dev/ | grep -i cache-control
curl -I https://your-project.pages.dev/assets/main-abc123.js | grep -i cache-control

# Confirm @view-transition rule is parsed (Chrome DevTools)
# Open DevTools > Animations panel, navigate between pages — transitions appear there

# Local Pages dev server
npx wrangler pages dev ./dist
```

## Related

- `vite-cloudflare-pages-build-optimization.md`
- `react-server-components-cloudflare-workers.md`

## Sources

- View Transitions API — https://developer.mozilla.org/en-US/docs/Web/API/View_Transitions_API
- Cross-document transitions — https://developer.chrome.com/docs/web-platform/view-transitions/cross-document
- Cloudflare Pages Headers — https://developers.cloudflare.com/pages/configuration/headers/
