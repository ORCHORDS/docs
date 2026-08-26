# Dark Mode with CSS Custom Properties and Cloudflare Pages Edge Detection

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-Case

Your app supports dark mode via a toggle that persists to `localStorage`. On the first page load users see a white flash before JavaScript reads the stored preference and applies the dark class. Additionally, the `prefers-color-scheme` media query is your fallback—but on some Cloudflare Pages routes you want to hint the preferred scheme in the HTML response so the browser can apply the correct stylesheet before rendering, eliminating the flash entirely.

---

## Context

The canonical approach to avoiding the dark-mode flash (FOUC) combines three layers:

1. **CSS custom properties** — all colours are defined as tokens, flipped by a single class or `data-theme` attribute on `<html>`.
2. **Inline `<script>` in `<head>`** — runs synchronously before the parser reaches `<body>`, reads `localStorage` and sets the attribute before the first paint.
3. **Cloudflare Pages edge hint (optional)** — the Worker reads the `Sec-CH-Prefers-Color-Scheme` client hint header and injects the correct `data-theme` into the HTML shell server-side, so even the inline script has the right starting value on the very first request.

Together these eliminate the flash in every scenario: first-ever visit (system fallback), subsequent visits (localStorage), and opt-in client-hints flows.

---

## 1. CSS Custom Properties Token Architecture

```css
/* styles/tokens.css */

/* 1. Light mode tokens — the baseline */
:root {
  --color-bg:           #ffffff;
  --color-bg-subtle:    #f8f9fa;
  --color-bg-muted:     #e9ecef;
  --color-surface:      #ffffff;
  --color-border:       #dee2e6;
  --color-text:         #212529;
  --color-text-muted:   #6c757d;
  --color-text-inverted:#ffffff;
  --color-accent:       #0d6efd;
  --color-accent-hover: #0b5ed7;
  --color-danger:       #dc3545;
  --color-success:      #198754;

  --shadow-sm: 0 1px 2px rgb(0 0 0 / 0.08);
  --shadow-md: 0 4px 6px rgb(0 0 0 / 0.10);
  --radius:    0.375rem;
  --transition: color 0.15s ease, background-color 0.15s ease, border-color 0.15s ease;
}

/* 2. System dark preference (no explicit user choice) */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --color-bg:           #0d1117;
    --color-bg-subtle:    #161b22;
    --color-bg-muted:     #21262d;
    --color-surface:      #1c2128;
    --color-border:       #30363d;
    --color-text:         #e6edf3;
    --color-text-muted:   #8b949e;
    --color-text-inverted:#0d1117;
    --color-accent:       #58a6ff;
    --color-accent-hover: #79c0ff;
    --color-danger:       #f85149;
    --color-success:      #3fb950;

    --shadow-sm: 0 1px 2px rgb(0 0 0 / 0.3);
    --shadow-md: 0 4px 6px rgb(0 0 0 / 0.4);
  }
}

/* 3. Explicit user choice — `data-theme` wins over system setting in both directions */
:root[data-theme="dark"] {
  --color-bg:           #0d1117;
  --color-bg-subtle:    #161b22;
  --color-bg-muted:     #21262d;
  --color-surface:      #1c2128;
  --color-border:       #30363d;
  --color-text:         #e6edf3;
  --color-text-muted:   #8b949e;
  --color-text-inverted:#0d1117;
  --color-accent:       #58a6ff;
  --color-accent-hover: #79c0ff;
  --color-danger:       #f85149;
  --color-success:      #3fb950;

  --shadow-sm: 0 1px 2px rgb(0 0 0 / 0.3);
  --shadow-md: 0 4px 6px rgb(0 0 0 / 0.4);
}

/* Give body an explicit background so transparent body doesn't borrow host theme */
body {
  background-color: var(--color-bg);
  color: var(--color-text);
  transition: var(--transition);
}
```

---

## 2. Anti-Flash Inline Script (No-JS Flash Elimination)

This script runs synchronously in `<head>`, before the browser paints the first frame:

```html
<!-- public/index.html or _worker.ts HTML shell -->
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <!-- Anti-flash: runs synchronously before body is parsed -->
  <script>
    (function () {
      try {
        var stored = localStorage.getItem('theme');
        if (stored === 'dark' || stored === 'light') {
          document.documentElement.setAttribute('data-theme', stored);
        } else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
          document.documentElement.setAttribute('data-theme', 'dark');
        }
      } catch (_) {
        // localStorage blocked (private mode, etc.) — system preference via CSS handles it
      }
    })();
  </script>
  <link rel="stylesheet"  />
</head>
```

The IIFE reads `localStorage` synchronously. If blocked (Firefox strict mode, Safari ITP), the CSS `@media (prefers-color-scheme: dark)` block applies automatically—zero dependency on the script succeeding.

---

## 3. Cloudflare Pages Middleware: Server-Side Theme Hint

```typescript
// functions/_middleware.ts
export const onRequest: PagesFunction = async ({ request, next }) => {
  const response = await next();

  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.includes('text/html')) return response;

  // Read the Client Hints header (requires Accept-CH negotiation on a prior visit)
  const schemePref = request.headers.get('Sec-CH-Prefers-Color-Scheme');
  if (!schemePref) return response;

  const theme = schemePref.toLowerCase().trim() === 'dark' ? 'dark' : 'light';

  // Inject data-theme onto <html> before the anti-flash script runs
  return new HTMLRewriter()
    .on('html', {
      element(el) {
        // Only set server-side hint; localStorage (client script) will override on next render
        el.setAttribute('data-theme-hint', theme);
      },
    })
    .on('head', {
      element(el) {
        // Also inject Accept-CH and Permissions-Policy headers via a meta equiv
        el.prepend(
          '<meta http-equiv="Accept-CH" content="Sec-CH-Prefers-Color-Scheme" />',
          { html: true },
        );
      },
    })
    .transform(
      new Response(response.body, {
        ...response,
        headers: new Headers({
          ...Object.fromEntries(response.headers),
          'Accept-CH': 'Sec-CH-Prefers-Color-Scheme',
          'Permissions-Policy': 'ch-prefers-color-scheme=(self)',
          'Vary': 'Sec-CH-Prefers-Color-Scheme',
        }),
      }),
    );
};
```

Update the anti-flash script to read both the `localStorage` value and the server hint:

```html
<script>
  (function () {
    try {
      var stored = localStorage.getItem('theme');
      var serverHint = document.documentElement.getAttribute('data-theme-hint');
      var preferred = stored || serverHint || (
        window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
      );
      document.documentElement.setAttribute('data-theme', preferred);
    } catch (_) {}
  })();
</script>
```

---

## 4. React Dark Mode Hook and Toggle

```typescript
// hooks/useTheme.ts
import { useState, useEffect, useCallback } from 'react';

type Theme = 'light' | 'dark' | 'system';

function getStoredTheme(): Theme {
  try {
    const v = localStorage.getItem('theme');
    if (v === 'light' || v === 'dark' || v === 'system') return v;
  } catch {}
  return 'system';
}

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === 'system') {
    root.removeAttribute('data-theme');
  } else {
    root.setAttribute('data-theme', theme);
  }
  try {
    localStorage.setItem('theme', theme);
  } catch {}
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(() => {
    if (typeof window === 'undefined') return 'system';
    return getStoredTheme();
  });

  // Sync system preference changes when theme === 'system'
  useEffect(() => {
    if (theme !== 'system') return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = () => {
      // Remove and re-set to trigger CSS re-evaluation
      document.documentElement.removeAttribute('data-theme');
    };
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, [theme]);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    applyTheme(next);
  }, []);

  const isDark =
    theme === 'dark' ||
    (theme === 'system' &&
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-color-scheme: dark)').matches);

  return { theme, setTheme, isDark };
}
```

---

## 5. Theme Toggle Component

```tsx
// components/ThemeToggle.tsx
import { useTheme } from '../hooks/useTheme';

type Theme = 'light' | 'dark' | 'system';

const LABELS: Record<Theme, string> = {
  light: 'Light',
  dark: 'Dark',
  system: 'System',
};

const ICONS: Record<Theme, string> = {
  light: '☀️',
  dark: '🌙',
  system: '💻',
};

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  return (
    <div role="group" aria-label="Select colour theme" className="flex rounded border overflow-hidden">
      {(['light', 'dark', 'system'] as const).map((t) => (
        <button
          key={t}
          type="button"
          onClick={() => setTheme(t)}
          aria-pressed={theme === t}
          className={[
            'px-3 py-1.5 text-sm flex items-center gap-1',
            theme === t
              ? 'bg-[var(--color-accent)] text-[var(--color-text-inverted)]'
              : 'bg-[var(--color-surface)] text-[var(--color-text)] hover:bg-[var(--color-bg-subtle)]',
          ].join(' ')}
        >
          <span aria-hidden>{ICONS[t]}</span>
          {LABELS[t]}
        </button>
      ))}
    </div>
  );
}
```

---

## 6. Using Design Tokens in Components

```tsx
// components/Card.tsx
export function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius)',
        boxShadow: 'var(--shadow-sm)',
        padding: '1.25rem',
      }}
    >
      <h2 style={{ color: 'var(--color-text)', marginBottom: '0.5rem' }}>{title}</h2>
      <p style={{ color: 'var(--color-text-muted)' }}>{children}</p>
    </div>
  );
}
```

With Tailwind CSS v4 (native CSS variables):

```tsx
// Tailwind v4 uses CSS variables directly; add to tailwind.config:
// theme.extend.colors.bg = 'var(--color-bg)'
<div className="bg-[var(--color-bg)] text-[var(--color-text)] border border-[var(--color-border)]">
```

---

## Anti-Patterns

- **Applying dark mode via a React state class toggle without the inline `<head>` script** — React state is not set until after hydration, causing a white flash on every page load. The inline script in `<head>` is mandatory for flash-free dark mode.
- **Using `document.body.classList` instead of `document.documentElement`** — The `@media (prefers-color-scheme: dark)` `:root` selector targets `<html>` (`documentElement`), not `<body>`. Toggling body classes creates specificity mismatches.
- **Defining dark-mode colours only inside the media query block** — Tokens that only exist in `@media (prefers-color-scheme: dark)` have no value when `[data-theme="light"]` is set on a system-dark device; `:root` must always define every token.
- **Storing theme in a cookie and reading it in the Worker without Vary** — Omitting `Vary: Cookie` from cached HTML responses causes all users to see the cached theme, ignoring their preference.
- **Animating all properties on theme change** — `transition: all` causes every CSS property to animate when the theme switches, including layout properties. Limit to `color`, `background-color`, and `border-color` to avoid janky transitions.

---

## Gotchas

- **Client Hints availability**: `Sec-CH-Prefers-Color-Scheme` is only sent by Chrome 93+ and Edge. Safari and Firefox do not support it. The server hint is a progressive enhancement; the CSS media query is always the fallback.
- **Vary header and Cloudflare caching**: Adding `Vary: Sec-CH-Prefers-Color-Scheme` tells Cloudflare's CDN to cache separate HTML responses per theme. This doubles your HTML cache slots. Only do this if the server hint provides measurable UX benefit for your audience.
- **`localStorage` in Workers**: Workers run on the server and have no `localStorage`. The anti-flash script runs in the browser; the Worker cannot read it. The `data-theme-hint` attribute is the bridge between server knowledge (client hints) and client execution (inline script).
- **SSR hydration with `data-theme`**: If your RSC / Worker injects `data-theme="dark"` and the client script also sets it, React's hydration will warn about a mismatched attribute if the values differ. Ensure the anti-flash script reads `data-theme-hint` (server signal) and `localStorage` (user choice), and only sets `data-theme` once with the resolved value.
- **iOS system dark mode lag**: On iOS, `prefers-color-scheme` can take a full second to update after the user changes their system setting. The `change` event on `matchMedia` fires reliably on iOS Safari 14+; ensure your `useTheme` hook listens for it when in `system` mode.
- **Tailwind `darkMode: 'selector'` vs `'media'`**: Tailwind's `dark:` utilities in selector mode target `.dark` or `[data-theme="dark"]`. Set `darkMode: ['selector', '[data-theme="dark"]']` in `tailwind.config.ts` to align with the pattern above.

---

## Verification

```bash
# 1. Confirm tokens are defined
curl -s https://your-app.pages.dev/styles/tokens.css | grep -- '--color-bg'

# 2. Confirm anti-flash script is in <head>
curl -s https://your-app.pages.dev/ | grep -A5 'Anti-flash'

# 3. Confirm Accept-CH header is present
curl -I https://your-app.pages.dev/ | grep -i 'accept-ch'

# 4. Simulate dark client hint, check data-theme-hint injection
curl -s https://your-app.pages.dev/ \
  -H 'Sec-CH-Prefers-Color-Scheme: dark' \
  | grep 'data-theme-hint'
# Expected: data-theme-hint="dark"

# 5. No flash in browser: open DevTools > Performance > record page load
# Check paint events: background should match theme without a white frame
```

---

## Related

- `css-custom-properties-theming.md`
- `css-light-dark-system-color-contract.md`
- `tailwind-dark-mode.md`
- `dark-mode-mobile-media-query-inconsistencies.md`
- `cloudflare-pages-headers-csp-mobile.md`

---

## Sources

- CSS Custom Properties — https://developer.mozilla.org/en-US/docs/Web/CSS/--*
- `prefers-color-scheme` — https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-color-scheme
- Client Hints: `Sec-CH-Prefers-Color-Scheme` — https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Sec-CH-Prefers-Color-Scheme
- HTMLRewriter — https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- Tailwind CSS dark mode — https://tailwindcss.com/docs/dark-mode
