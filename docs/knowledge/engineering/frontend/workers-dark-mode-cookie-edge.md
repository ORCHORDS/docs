# Edge-Side Dark Mode Preference Handling with Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your site supports a light/dark mode toggle. If you implement it purely in JavaScript, users on their preferred dark theme see a flash of light content (FOUC) before the script runs and adds the `dark` class to `<html>`. If you implement it with `prefers-color-scheme` alone, the user's explicit in-app toggle has no effect across page loads. You need the server — or the edge — to know the user's preference before the first byte of HTML is sent.

## Context

The classic FOUC solution is an inline `<script>` in `<head>` that reads `localStorage` and sets the class synchronously, before any render. This works but:

- Blocks parsing briefly (though it's tiny).
- Requires JavaScript; fails for `<noscript>` users.
- Does not propagate the preference to `<meta name="theme-color">`, OG images, or server-rendered components that need to pick between two image variants.

A Cloudflare Worker can read the preference cookie and use `HTMLRewriter` to inject the correct class on `<html>` during the streaming response — before the browser renders a single pixel. The result is zero-FOUC without an inline script.

## Solution

### 1. CSS custom-property approach (theme-aware)

```css
/* styles/theme.css */

:root {
  --color-bg:        #ffffff;
  --color-text:      #111827;
  --color-surface:   #f9fafb;
  --color-border:    #e5e7eb;
  --color-accent:    #6366f1;
  --color-accent-fg: #ffffff;
}

/* System-level dark preference — fallback when no explicit choice is set */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme]) {
    --color-bg:      #111827;
    --color-text:    #f9fafb;
    --color-surface: #1f2937;
    --color-border:  #374151;
    --color-accent:  #818cf8;
  }
}

/* Explicit dark choice — set by Worker via data-theme="dark" on <html> */
:root[data-theme="dark"] {
  --color-bg:      #111827;
  --color-text:    #f9fafb;
  --color-surface: #1f2937;
  --color-border:  #374151;
  --color-accent:  #818cf8;
}

/* Explicit light choice — overrides prefers-color-scheme: dark */
:root[data-theme="light"] {
  --color-bg:        #ffffff;
  --color-text:      #111827;
  --color-surface:   #f9fafb;
  --color-border:    #e5e7eb;
  --color-accent:    #6366f1;
}

/* Component usage */
body {
  background-color: var(--color-bg);
  color:            var(--color-text);
}
```

### 2. Worker: read preference cookie and inject `data-theme`

```typescript
// worker/index.ts
import { Env } from './types';

const COOKIE_NAME  = 'theme';
const VALID_THEMES = new Set(['light', 'dark']);

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Preference toggle API: POST /api/theme
    if (url.pathname === '/api/theme' && request.method === 'POST') {
      return handleThemeToggle(request);
    }

    // For all HTML responses, inject the theme attribute
    const upstream = await fetch(request);
    const ct = upstream.headers.get('Content-Type') ?? '';
    if (!ct.includes('text/html')) return upstream; // pass through non-HTML

    const theme = parseThemeCookie(request);
    if (!theme) return upstream; // no explicit preference; CSS media query handles it

    return new HTMLRewriter()
      .on('html', new ThemeAttributeInjector(theme))
      .on('meta[name="theme-color"]', new ThemeColorUpdater(theme))
      .transform(upstream);
  },
};

function parseThemeCookie(request: Request): 'light' | 'dark' | null {
  const cookieHeader = request.headers.get('Cookie') ?? '';
  for (const part of cookieHeader.split(';')) {
    const [key, value] = part.trim().split('=');
    if (key?.trim() === COOKIE_NAME) {
      const val = decodeURIComponent(value ?? '');
      return VALID_THEMES.has(val) ? (val as 'light' | 'dark') : null;
    }
  }
  return null;
}
```

### 3. HTMLRewriter handlers

```typescript
// worker/handlers.ts

export class ThemeAttributeInjector implements HTMLRewriterElementContentHandlers {
  constructor(private readonly theme: 'light' | 'dark') {}

  element(el: Element) {
    // Set data-theme on the root <html> element
    // This fires before any content is streamed to the client
    el.setAttribute('data-theme', this.theme);
  }
}

export class ThemeColorUpdater implements HTMLRewriterElementContentHandlers {
  private readonly META_COLORS: Record<'light' | 'dark', string> = {
    light: '#ffffff',
    dark:  '#111827',
  };

  constructor(private readonly theme: 'light' | 'dark') {}

  element(el: Element) {
    // Update the browser chrome colour to match the theme
    el.setAttribute('content', this.META_COLORS[this.theme]);
  }
}
```

### 4. Theme toggle API endpoint

```typescript
// worker/toggle.ts

const COOKIE_MAX_AGE = 60 * 60 * 24 * 365; // 1 year

export async function handleThemeToggle(request: Request): Promise<Response> {
  let desired: 'light' | 'dark' = 'dark';

  try {
    const body = await request.json() as { theme?: string };
    if (body.theme === 'light' || body.theme === 'dark') {
      desired = body.theme;
    }
  } catch {
    return new Response(JSON.stringify({ error: 'Invalid body' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // SameSite=Lax — safe for cross-page navigation; Secure in production
  const cookie = [
    `theme=${desired}`,
    `Max-Age=${COOKIE_MAX_AGE}`,
    'Path=/',
    'SameSite=Lax',
    'Secure',
  ].join('; ');

  return new Response(JSON.stringify({ theme: desired }), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      'Set-Cookie':   cookie,
    },
  });
}
```

### 5. Client-side toggle (no framework)

```typescript
// public/js/theme-toggle.ts

document.querySelector<HTMLButtonElement>('#theme-toggle')?.addEventListener('click', async () => {
  const current  = document.documentElement.dataset.theme ?? detectSystemTheme();
  const desired  = current === 'dark' ? 'light' : 'dark';

  // Optimistic update: apply immediately for snappy UX
  document.documentElement.dataset.theme = desired;
  updateToggleLabel(desired);

  // Persist via the Worker API so the next page load is correct
  try {
    await fetch('/api/theme', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ theme: desired }),
    });
  } catch (err) {
    console.warn('[theme] Failed to persist preference:', err);
    // Revert optimistic update on error
    document.documentElement.dataset.theme = current;
    updateToggleLabel(current);
  }
});

function detectSystemTheme(): 'light' | 'dark' {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function updateToggleLabel(theme: 'light' | 'dark'): void {
  const btn = document.querySelector<HTMLButtonElement>('#theme-toggle');
  if (btn) btn.textContent = theme === 'dark' ? '☀️ Light mode' : '🌙 Dark mode';
}

// On first load with no cookie, respect system preference visually
if (!document.documentElement.dataset.theme) {
  // Nothing to do — CSS `@media (prefers-color-scheme: dark)` handles it
  // But sync the toggle label to the effective theme
  updateToggleLabel(detectSystemTheme());
}
```

### 6. HTML markup

```html
<!-- public/index.html -->
<!doctype html>
<!-- Worker injects data-theme here before streaming -->
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="theme-color" content="#ffffff"> <!-- updated by Worker to match theme -->
  <title>My Site</title>
  <link rel="stylesheet" >
</head>
<body>
  <header>
    <button id="theme-toggle" type="button">🌙 Dark mode</button>
  </header>
  <main>
    <h1>Hello</h1>
  </main>
  <script type="module" ></script>
</body>
</html>
```

### 7. Types and wrangler.toml

```typescript
// worker/types.ts
export interface Env {
  // No bindings required for this feature;
  // add KV if you want to store preferences server-side per user
}
```

```toml
# wrangler.toml
name = "dark-mode-worker"
main = "worker/index.ts"
compatibility_date = "2025-01-01"
```

## Implementation Details

- **HTMLRewriter fires on the `html` element** which is the first tag in the document — injected before any `<head>` or `<body>` content is sent. This guarantees no flash.
- **`data-theme` vs. a class name** — using a data attribute makes the CSS selector specific (`[data-theme="dark"]`) and explicit. A class name (`dark`) is simpler but collides with utility frameworks.
- **`prefers-color-scheme` fallback** — when no cookie is present, `data-theme` is absent, and the CSS `@media` query fires. This means first-time visitors automatically get the correct theme without any JavaScript or cookie.
- **`Secure` cookie flag** — require HTTPS. In `wrangler dev` (HTTP) the browser ignores the `Secure` flag; production automatically enforces it.
- **`SameSite=Lax`** allows the cookie to be sent on top-level navigations (clicking a link to your site) which is the right default for a theme preference.

## Anti-patterns

- **Setting `data-theme` in a `<script>` in `<head>`** — works, but blocks parser for a tick; the Worker approach is strictly cleaner.
- **Using `localStorage` as the sole store** — `localStorage` is unavailable on the first server request. The Worker/cookie approach works on any reload without JavaScript.
- **Caching personalised HTML at the CDN edge** — a response with `data-theme` injected is specific to a cookie value. Set `Vary: Cookie` and `Cache-Control: private` on HTML responses when theme injection is active.
- **Hardcoding hex colours in JS** — define all colours as CSS custom properties; the toggle should only switch the `data-theme` attribute, not update inline styles.

## Gotchas

- If the static asset is served from Workers Assets (the `assets` binding) and you proxy through a Worker, the `fetch(request)` inside the Worker correctly fetches from the asset binding. Verify this in `wrangler dev` — the request must pass through the Worker, not bypass it via a direct asset URL.
- HTMLRewriter `on('html', ...)` matches the `<html>` opening tag only once. It cannot be used to match the closing `</html>` tag.
- Cookie parsing is case-sensitive for the cookie name. `Theme=dark` is different from `theme=dark`.
- The `theme-color` meta tag affects mobile browser chrome colour. On desktop it has no effect. Only update it when you care about mobile polish.
- `fetch(request)` inside a Worker re-fetches using the same URL, which can cause a redirect loop if the Worker handles all routes and the asset origin is the same Worker URL. Use an internal origin (e.g., Workers Assets binding or a separate R2-backed host) for the upstream.

## Verification

1. `wrangler dev` — set the cookie manually: `document.cookie = 'theme=dark; path=/'`, then hard-reload. The `<html>` tag must have `data-theme="dark"` in the page source (view-source:) without any JavaScript running.
2. Confirm no FOUC: use Chrome DevTools → Performance tab → record a reload, inspect frames — background should be dark from frame 1.
3. Toggle via the button — confirm the cookie is set (`Application → Cookies`) and a second reload preserves the theme.
4. Clear cookies — confirm the system preference (`prefers-color-scheme`) is respected via the CSS media query alone.
5. `curl -H 'Cookie: theme=dark' http://localhost:8787/` and inspect the HTML — `<html data-theme="dark">` should appear.

## Related

- `workers-edge-personalisation-htmlrewriter.md` — HTMLRewriter patterns for other personalisations
- `workers-islands-architecture-partial-hydration.md` — streaming HTML shell architecture
- `workers-static-form-handler-d1.md` — cookie handling in Workers

## Sources

- Cloudflare HTMLRewriter: https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- MDN prefers-color-scheme: https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-color-scheme
- web.dev FOUC: https://web.dev/articles/prefers-color-scheme
- HTTP cookies (MDN): https://developer.mozilla.org/en-US/docs/Web/HTTP/Cookies
