# Dark Mode with Edge Cookie Detection on Cloudflare Pages

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

Your app supports light and dark themes via CSS custom properties and a `data-theme` attribute on `<html>`. Users who have explicitly chosen a theme — stored in a cookie — see a flash of the wrong theme on page load: the HTML arrives without the attribute, React hydrates, then a `useEffect` reads the cookie and applies the theme class. The flash lasts 50–300 ms and is visible even on fast connections.

---

## Context

The root cause is timing: `prefers-color-scheme` is available before JavaScript runs, but a stored user preference in a cookie is not — it requires JS to read `document.cookie`. The fix is to read the cookie at the **edge** (a Cloudflare Pages Function), inject `data-theme` into the HTML response before it reaches the browser, and let CSS use it immediately. No JavaScript is needed for the initial render; React hydrates with the correct state already in the DOM.

This pattern differs from:
- **`prefers-color-scheme` only** — respects the OS setting but ignores the user's in-app override.
- **Inline `<script>` before `</head>`** — reads `document.cookie` client-side before paint; eliminates the flash but requires a blocking script.
- **Cloudflare Workers with HTMLRewriter** — the same technique as this article but requires a full Workers deployment rather than a Pages Function.

Cloudflare Pages Functions run as lightweight Workers on every request within your Pages project, making them the lowest-friction location to run the rewrite.

---

## Section 1: Setting the preference cookie from the frontend

```typescript
// lib/theme.ts
export type Theme = "light" | "dark" | "system";

const COOKIE_NAME = "theme";
const COOKIE_MAX_AGE = 60 * 60 * 24 * 365; // 1 year

export function setThemeCookie(theme: Theme): void {
  // SameSite=Lax is safe for a first-party preference cookie.
  // Omit Secure in dev; the Pages Function will run on HTTPS in production.
  document.cookie = [
    `${COOKIE_NAME}=${theme}`,
    `Max-Age=${COOKIE_MAX_AGE}`,
    "Path=/",
    "SameSite=Lax",
  ].join("; ");
}

export function getThemeCookie(): Theme | null {
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${COOKIE_NAME}=`));
  if (!match) return null;
  const value = match.split("=")[1];
  return value === "light" || value === "dark" || value === "system"
    ? value
    : null;
}
```

---

## Section 2: Cloudflare Pages Function to inject `data-theme`

Place this file at `functions/_middleware.ts`. Cloudflare Pages runs it on every request that matches a page (not static assets).

```typescript
// functions/_middleware.ts
import type { PagesFunction } from "@cloudflare/workers-types";

const VALID_THEMES = new Set(["light", "dark"]);

function parseThemeCookie(cookieHeader: string | null): string | null {
  if (!cookieHeader) return null;
  for (const part of cookieHeader.split(";")) {
    const [key, value] = part.trim().split("=");
    if (key === "theme" && value && VALID_THEMES.has(value)) {
      return value;
    }
  }
  return null;
}

export const onRequest: PagesFunction = async (context) => {
  const response = await context.next();

  // Only rewrite HTML responses — leave JS, CSS, images, API responses alone
  const contentType = response.headers.get("Content-Type") ?? "";
  if (!contentType.includes("text/html")) {
    return response;
  }

  const cookieHeader = context.request.headers.get("Cookie");
  const theme = parseThemeCookie(cookieHeader);

  // "system" and absent cookie both mean: let CSS media query decide.
  // Only inject data-theme for explicit "light" or "dark" overrides.
  if (!theme) {
    return response;
  }

  // HTMLRewriter patches the <html> tag in the streaming response.
  // No buffering — the rewrite happens as bytes flow through.
  return new HTMLRewriter()
    .on("html", {
      element(el) {
        el.setAttribute("data-theme", theme);
      },
    })
    .transform(response);
};
```

---

## Section 3: CSS custom properties that respond to `data-theme`

```css
/* styles/theme.css */

/* Base tokens — light theme by default */
:root {
  --color-bg: #ffffff;
  --color-surface: #f5f5f5;
  --color-text: #111111;
  --color-text-muted: #555555;
  --color-border: #dddddd;
  --color-accent: #0066cc;
  --color-accent-hover: #0052a3;
}

/* System dark preference, no explicit override */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --color-bg: #0f0f0f;
    --color-surface: #1a1a1a;
    --color-text: #f0f0f0;
    --color-text-muted: #aaaaaa;
    --color-border: #333333;
    --color-accent: #4da3ff;
    --color-accent-hover: #79bcff;
  }
}

/* Explicit dark override — wins over everything, including media query */
:root[data-theme="dark"] {
  --color-bg: #0f0f0f;
  --color-surface: #1a1a1a;
  --color-text: #f0f0f0;
  --color-text-muted: #aaaaaa;
  --color-border: #333333;
  --color-accent: #4da3ff;
  --color-accent-hover: #79bcff;
}

/* Explicit light override — wins over dark media query */
:root[data-theme="light"] {
  --color-bg: #ffffff;
  --color-surface: #f5f5f5;
  --color-text: #111111;
  --color-text-muted: #555555;
  --color-border: #dddddd;
  --color-accent: #0066cc;
  --color-accent-hover: #0052a3;
}

body {
  background-color: var(--color-bg);
  color: var(--color-text);
}
```

The cascade ensures:
- No `data-theme` + OS dark → dark tokens from the media query.
- `data-theme="dark"` → dark tokens regardless of OS.
- `data-theme="light"` → light tokens, overriding a dark OS preference.

---

## Section 4: React theme context and toggle

```tsx
// contexts/ThemeContext.tsx
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { setThemeCookie, getThemeCookie, type Theme } from "../lib/theme";

interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  resolvedTheme: "light" | "dark";
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  // Initialise from cookie synchronously — by now the cookie exists client-side too.
  // The edge already wrote data-theme to the HTML, so this useState just syncs
  // the React state with what the DOM already reflects. No flash.
  const [theme, setThemeState] = useState<Theme>(
    () => getThemeCookie() ?? "system",
  );

  const resolvedTheme: "light" | "dark" =
    theme !== "system"
      ? theme
      : typeof window !== "undefined" &&
          window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";

  function setTheme(next: Theme) {
    setThemeState(next);
    setThemeCookie(next);

    // Update the attribute immediately — next page load will also be correct
    // because the edge will read the updated cookie.
    if (next === "system") {
      document.documentElement.removeAttribute("data-theme");
    } else {
      document.documentElement.setAttribute("data-theme", next);
    }
  }

  // Keep data-theme in sync if the user changes OS preference while "system"
  useEffect(() => {
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e: MediaQueryListEvent) => {
      document.documentElement.removeAttribute("data-theme");
      // CSS handles the rest via the media query; no attribute is correct for "system"
    };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, setTheme, resolvedTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used inside <ThemeProvider>");
  return ctx;
}
```

---

## Section 5: Theme toggle component

```tsx
// components/ThemeToggle.tsx
import { useTheme } from "../contexts/ThemeContext";
import type { Theme } from "../lib/theme";

const OPTIONS: { value: Theme; label: string }[] = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
];

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  return (
    <fieldset style={{ border: "none", padding: 0, margin: 0 }}>
      <legend className="sr-only">Theme</legend>
      {OPTIONS.map((opt) => (
        <label key={opt.value} style={{ marginRight: "0.75rem" }}>
          <input
            type="radio"
            name="theme"
            value={opt.value}
            checked={theme === opt.value}
            onChange={() => setTheme(opt.value)}
          />
          {" "}{opt.label}
        </label>
      ))}
    </fieldset>
  );
}
```

---

## Section 6: Hydration safety

Server rendering (SSR on Cloudflare Pages with a framework adapter) adds a wrinkle: the server renders JSX without access to client-side cookie state, so `getThemeCookie()` returns `null` during SSR. The edge injects `data-theme` into the raw HTML, but the React tree is rendered from `"system"` by default.

If the server renders a theme-sensitive component (e.g., a conditional icon), the hydrated markup may differ from the server-rendered markup, causing a hydration mismatch.

Two safe approaches:

**Option A — Defer theme-sensitive rendering to the client:**

```tsx
import { useEffect, useState } from "react";

export function ThemeIcon() {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    // Return a placeholder that has no theme dependency
    return <span style={{ width: 24, height: 24, display: "inline-block" }} aria-hidden />;
  }

  return resolvedTheme === "dark" ? <MoonIcon /> : <SunIcon />;
}
```

**Option B — Pass the theme via a cookie in a server loader and initialise context on the server.** Requires a framework that exposes request headers during SSR (e.g., Remix/React Router with a Cloudflare adapter or Next.js with `cookies()`).

```typescript
// app/root.tsx (Remix)
import { parseCookies } from "~/lib/cookies.server";

export async function loader({ request }: LoaderArgs) {
  const cookies = parseCookies(request.headers.get("Cookie") ?? "");
  const theme = (cookies["theme"] as Theme | undefined) ?? "system";
  return json({ theme });
}
```

The loader result initialises `ThemeProvider`'s default state, eliminating mismatches because both SSR and hydration start from the same value.

---

## Anti-patterns

- **Reading `document.cookie` in `useEffect`** — fires after paint, causing the flash this article is designed to prevent.
- **Storing the theme in `localStorage` instead of a cookie** — `localStorage` is inaccessible at the edge and requires a blocking inline script to avoid the flash.
- **Injecting `data-theme` via an inline `<script>` before `<body>`** — works but adds a render-blocking script. The edge rewrite is zero-JS cost.
- **Rewriting all responses in the middleware** — check `Content-Type: text/html` before running `HTMLRewriter`. Rewriting binary assets (images, fonts) corrupts them.
- **Using `httpOnly` for the theme cookie** — an `httpOnly` cookie is not readable by `document.cookie`, so the client cannot sync React state without an API call. Theme is not a secret; omit `httpOnly`.
- **Validating themes loosely** — accept only `"light"` and `"dark"` in the middleware. An attacker-controlled `data-theme` value would flow into the HTML response.

---

## Gotchas

- **`HTMLRewriter` streams the response** — it does not buffer the full document. This is a feature (low latency), but it means the `<html>` element must appear early in the stream. It always does in well-formed HTML.
- **Pages Functions path** — the middleware must be at `functions/_middleware.ts` to apply to all page routes. A file at `functions/index.ts` only intercepts the root route.
- **Local development** — `wrangler pages dev` runs Pages Functions locally, including the middleware. Test the cookie injection by setting `document.cookie = "theme=dark"` in the console and refreshing.
- **Cache interaction** — if you cache HTML responses at the edge (via `Cache-Control` or Cloudflare's cache), different users with different cookies must receive different cached responses. Either bypass the cache for HTML (`Cache-Control: private`) or vary the cache on the `Cookie` header (`Vary: Cookie`). Caching HTML with a user-preference cookie usually is not worth the complexity; leave HTML uncached and let Cloudflare cache only static assets.
- **Cookie `Path=/`** — without an explicit path the cookie's scope defaults to the current path, which means a preference set on `/settings` would not apply to `/dashboard`. Always set `Path=/` for a site-wide preference.

---

## Verification

```bash
# 1. Start local Pages dev server
npx wrangler pages dev ./dist --port 5173

# 2. Open http://localhost:5173 in a browser
# 3. In DevTools console:
document.cookie = "theme=dark; Path=/";
location.reload();
# Expect: <html data-theme="dark"> in the Elements panel before
# any JS has executed (check with JS disabled or in "View source").

# 4. Switch to light:
document.cookie = "theme=light; Path=/";
location.reload();
# Expect: <html data-theme="light">, no flash.

# 5. Clear the cookie:
document.cookie = "theme=; Max-Age=0; Path=/";
location.reload();
# Expect: no data-theme attribute on <html>.

# 6. Confirm no hydration mismatch warnings in the console.
```

---

## Related

- `tailwind-dark-mode.md`
- `dark-mode-mobile-media-query-inconsistencies.md`
- `css-light-dark-system-color-contract.md`
- `css-custom-properties-theming.md`
- `cloudflare-pages-headers-csp-mobile.md`
- `web-components-cloudflare-workers-html-rewriter.md`

---

## Sources

- Cloudflare Pages Functions — Middleware: https://developers.cloudflare.com/pages/functions/middleware/
- Cloudflare HTMLRewriter API: https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- CSS `prefers-color-scheme`: https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-color-scheme
- Next.js theming without flash (next-themes): https://github.com/pacocoursey/next-themes
