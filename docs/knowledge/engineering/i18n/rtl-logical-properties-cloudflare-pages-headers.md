# Right-to-Left Layout: CSS Logical Properties and Cloudflare Pages Headers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Your application supports Arabic, Hebrew, or Persian (RTL languages) alongside LTR languages. You are deploying on Cloudflare Pages. The problems you hit:

- Adding `dir="rtl"` to `<html>` causes margins, paddings, floats, and positioned elements to mirror correctly in Arabic but your CSS still uses `margin-left`, `padding-right`, `left: 0` – which do not flip
- The RTL stylesheet is served regardless of locale, inflating bundle size for LTR users
- You need `Content-Security-Policy` and `X-Content-Type-Options` headers that do not interfere with inline styles required by your RTL CSS
- Arabic and Hebrew fonts require specific `font-feature-settings` and `text-rendering` values that collide with your base stylesheet

---

## Context

**CSS Logical Properties** (Level 3 specification, broadly supported as of 2024) replace direction-sensitive physical properties with flow-relative equivalents:

| Physical (avoid) | Logical (use) | Flow |
|---|---|---|
| `margin-left` | `margin-inline-start` | writing direction start |
| `margin-right` | `margin-inline-end` | writing direction end |
| `padding-top` | `padding-block-start` | block start |
| `left: 0` | `inset-inline-start: 0` | inline start |
| `border-right` | `border-inline-end` | inline end |
| `text-align: left` | `text-align: start` | start of line |
| `float: left` | `float: inline-start` | inline start |

When `dir="rtl"` is on a container, `inline-start` becomes the right edge, so layouts mirror automatically with zero JavaScript.

**Cloudflare Pages `_headers` file** is a plain-text file at the root of your publish directory that injects HTTP headers on every matched route. It is processed at the edge, not by your origin, making it the right place for:

- Security headers (`Content-Security-Policy`, `X-Frame-Options`)
- `Content-Language` per locale path
- `Cache-Control` for RTL assets
- `Link` preload hints for Arabic/Hebrew fonts

---

## Step 1: Replace Physical Properties with Logical Properties

### Before (physical, breaks RTL)

```css
.card {
  margin-left: 16px;
  margin-right: 8px;
  padding-left: 24px;
  border-right: 2px solid var(--border);
  float: left;
  text-align: left;
}

.dropdown {
  left: 0;
  right: auto;
}
```

### After (logical, works in both directions)

```css
.card {
  margin-inline-start: 16px;
  margin-inline-end: 8px;
  padding-inline-start: 24px;
  border-inline-end: 2px solid var(--border);
  float: inline-start;
  text-align: start;
}

.dropdown {
  inset-inline-start: 0;
  inset-inline-end: auto;
}
```

### Full logical property cheat-sheet for common patterns

```css
/* Spacing */
.el {
  /* Block axis (top/bottom in horizontal writing) */
  margin-block:        var(--space-4);
  margin-block-start:  var(--space-4);  /* top */
  margin-block-end:    var(--space-4);  /* bottom */
  padding-block:       var(--space-2);

  /* Inline axis (left/right in horizontal writing) */
  margin-inline:       var(--space-4);
  margin-inline-start: var(--space-4);  /* left in LTR, right in RTL */
  margin-inline-end:   var(--space-4);  /* right in LTR, left in RTL */
  padding-inline:      var(--space-2);
}

/* Sizing */
.el {
  inline-size:     100%;   /* width */
  block-size:      auto;   /* height */
  min-inline-size: 200px;
  max-block-size:  400px;
}

/* Positioning */
.el {
  position: absolute;
  inset-block-start:  0;   /* top */
  inset-block-end:    0;   /* bottom */
  inset-inline-start: 0;   /* left in LTR, right in RTL */
  inset-inline-end:   0;   /* right in LTR, left in RTL */

  /* Shorthand: block-start block-end inline-start inline-end */
  inset: 0 0 0 0;
}

/* Borders */
.el {
  border-block:        1px solid var(--border);
  border-block-start:  2px solid var(--accent);
  border-inline-start: 4px solid var(--highlight);
  border-inline-end:   1px solid var(--border);
  border-start-start-radius: 8px; /* top-left in LTR, top-right in RTL */
  border-start-end-radius:   8px; /* top-right in LTR, top-left in RTL */
}
```

---

## Step 2: Setting `dir` at the HTML Level

```typescript
// src/middleware/dir-injection.ts  (Cloudflare Worker or Pages Function)

const RTL_LOCALES = new Set(['ar', 'he', 'fa', 'ur', 'yi', 'dv']);

export function getTextDirection(locale: string): 'rtl' | 'ltr' {
  const base = locale.split('-')[0].toLowerCase();
  return RTL_LOCALES.has(base) ? 'rtl' : 'ltr';
}

/**
 * Inject dir and lang attributes into the <html> tag of an SSR response.
 */
export function injectDirAndLang(html: string, locale: string): string {
  const dir = getTextDirection(locale);
  return html.replace(
    /(<html)([^>]*)(>)/i,
    (_, open, attrs, close) => {
      // Remove any existing lang/dir to avoid duplicates
      const cleaned = attrs.replace(/\s*(lang|dir)="[^"]*"/gi, '');
      return `${open}${cleaned} lang="${locale}" dir="${dir}"${close}`;
    }
  );
}
```

---

## Step 3: Per-Locale Font Loading

Arabic and Hebrew require specific font families. Load them conditionally based on locale:

```html
<!-- In <head>, rendered by the Worker/Pages Function -->
<% if (locale === 'ar' || locale === 'fa') { %>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link
  rel="stylesheet"
  href="https://fonts.googleapis.com/css2?family=Noto+Sans+Arabic:wght@400;600;700&display=swap"
>
<style>
  :root[lang="ar"],
  :root[lang="fa"] {
    --font-body: 'Noto Sans Arabic', 'Segoe UI', Tahoma, Arial, sans-serif;
    font-feature-settings: "kern" 1;
    text-rendering: optimizeLegibility;
    /* Arabic text generally needs slightly larger line-height */
    --line-height-body: 1.8;
  }
</style>
<% } %>
<% if (locale === 'he') { %>
<link
  rel="stylesheet"
  href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;600;700&display=swap"
>
<style>
  :root[lang="he"] {
    --font-body: 'Heebo', 'Arial Hebrew', Arial, sans-serif;
    --line-height-body: 1.7;
  }
</style>
<% } %>
```

---

## Step 4: Cloudflare Pages `_headers` File

The `_headers` file lives at the root of your Pages build output (same level as `index.html`). Cloudflare Pages processes it at the edge before returning the response.

```
# _headers

# ─── Security headers applied to all routes ────────────────────────────────
/*
  X-Content-Type-Options: nosniff
  X-Frame-Options: SAMEORIGIN
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()
  # Note: no Content-Security-Policy here because RTL pages may use
  # inline styles injected by the Worker. Set CSP via the Worker instead
  # so you can compute a nonce or hash at request time.

# ─── Arabic locale ─────────────────────────────────────────────────────────
/ar/*
  Content-Language: ar
  Cache-Control: public, max-age=0, must-revalidate
  # Vary by Accept-Language so CDN doesn't serve AR pages to EN users
  Vary: Accept-Language

# ─── Hebrew locale ─────────────────────────────────────────────────────────
/he/*
  Content-Language: he
  Cache-Control: public, max-age=0, must-revalidate
  Vary: Accept-Language

# ─── Persian locale ────────────────────────────────────────────────────────
/fa/*
  Content-Language: fa
  Cache-Control: public, max-age=0, must-revalidate
  Vary: Accept-Language

# ─── LTR locales (example) ─────────────────────────────────────────────────
/en/*
  Content-Language: en
  Cache-Control: public, max-age=0, must-revalidate
  Vary: Accept-Language

/fr/*
  Content-Language: fr
  Cache-Control: public, max-age=0, must-revalidate
  Vary: Accept-Language

# ─── RTL-specific font assets: long cache ──────────────────────────────────
/fonts/arabic/*
  Cache-Control: public, max-age=31536000, immutable

/fonts/hebrew/*
  Cache-Control: public, max-age=31536000, immutable

# ─── API routes: no Content-Language (JSON, not HTML) ──────────────────────
/api/*
  Cache-Control: no-store
```

### Generating the `_headers` file at build time

If you support many locales, generate `_headers` programmatically:

```typescript
// scripts/generate-headers.ts
import { writeFileSync } from 'fs';

const LOCALES = [
  { code: 'en', dir: 'ltr' },
  { code: 'fr', dir: 'ltr' },
  { code: 'de', dir: 'ltr' },
  { code: 'ar', dir: 'rtl' },
  { code: 'he', dir: 'rtl' },
  { code: 'fa', dir: 'rtl' },
];

const lines: string[] = [
  '# Auto-generated by scripts/generate-headers.ts – do not edit manually',
  '',
  '/*',
  '  X-Content-Type-Options: nosniff',
  '  X-Frame-Options: SAMEORIGIN',
  '  Referrer-Policy: strict-origin-when-cross-origin',
  '',
];

for (const { code } of LOCALES) {
  lines.push(`/${code}/*`);
  lines.push(`  Content-Language: ${code}`);
  lines.push(`  Cache-Control: public, max-age=0, must-revalidate`);
  lines.push(`  Vary: Accept-Language`);
  lines.push('');
}

writeFileSync('public/_headers', lines.join('\n'), 'utf-8');
console.log('Generated public/_headers');
```

Add to your build script:

```json
{
  "scripts": {
    "build": "next build && node scripts/generate-headers.ts"
  }
}
```

---

## Step 5: RTL-Aware Component Pattern (React)

```tsx
// components/LocalizedContainer.tsx
import { type ReactNode } from 'react';

interface Props {
  locale:   string;
  children: ReactNode;
}

const RTL_LOCALES = ['ar', 'he', 'fa', 'ur'];

export function LocalizedContainer({ locale, children }: Props) {
  const base = locale.split('-')[0];
  const dir  = RTL_LOCALES.includes(base) ? 'rtl' : 'ltr';

  return (
    <div
      lang={locale}
      dir={dir}
      style={{
        // Use logical properties in inline styles too
        // (React 19+ supports them natively as camelCase)
        paddingInline:       '1rem',
        marginInlineStart:   dir === 'rtl' ? '0' : 'auto',
      }}
    >
      {children}
    </div>
  );
}
```

---

## Step 6: Logical Properties in Tailwind CSS

Tailwind v3.3+ ships logical utility classes:

```html
<!-- Physical (breaks RTL) -->
<div class="ml-4 pr-6 text-left border-r">...</div>

<!-- Logical (works in both directions) -->
<div class="ms-4 pe-6 text-start border-e">...</div>
```

| Physical | Logical Tailwind | Meaning |
|---|---|---|
| `ml-*` | `ms-*` | margin-inline-start |
| `mr-*` | `me-*` | margin-inline-end |
| `pl-*` | `ps-*` | padding-inline-start |
| `pr-*` | `pe-*` | padding-inline-end |
| `left-*` | `start-*` | inset-inline-start |
| `right-*` | `end-*` | inset-inline-end |
| `text-left` | `text-start` | text-align: start |
| `border-l` | `border-s` | border-inline-start |
| `rounded-l` | `rounded-s` | border-start-*-radius |

Enable in `tailwind.config.js`:

```js
module.exports = {
  // No special config needed for v3.3+; logical classes are included.
  // For Tailwind v3.2 and below, use the tailwindcss-logical plugin.
};
```

---

## Anti-Patterns

- **`direction: rtl` in CSS instead of `dir="rtl"` on HTML.** The CSS property affects only that element; the HTML attribute propagates to the browser's BiDi algorithm, form controls, and `scrollbar-side`. Always set the HTML attribute.
- **Using `transform: scaleX(-1)` to flip icons.** Some icons (arrows) flip correctly; others (checkmarks, logos) must not flip. Use SVG `dir`-aware icons or icon font ligatures instead.
- **Combining `text-align: center` with inline-start padding.** In RTL, `center` is fine but `start`-padding on a centered element can produce asymmetric results. Keep alignment and spacing concerns separate.
- **Relying on `_headers` for CSP nonces.** Cloudflare Pages `_headers` is static; it cannot compute per-request nonces. Use a Pages Function (middleware) to generate nonces and set CSP as a dynamic header.
- **Setting `Cache-Control: public, max-age=86400` on locale HTML pages without `Vary: Accept-Language`.** Without `Vary`, Cloudflare's edge cache may serve the French response to German users.

---

## Gotchas

- **`_headers` is case-sensitive for paths.** `/Ar/*` will not match `/ar/products`. Always use lowercase locale codes in paths.
- **`_headers` header values are merged, not overridden, with headers set by Pages Functions.** If your Pages Function sets `Cache-Control` and `_headers` also sets it, the `_headers` value wins. Document which layer owns which header.
- **Cloudflare Pages does not support wildcard path segments in `_headers`.** `/*/products` is not valid. Use `/ar/products` (literal) or `/ar/*` (prefix).
- **`border-start-start-radius` applies to the block-start / inline-start corner.** In a horizontal LTR layout this is the top-left corner. In RTL it is the top-right corner. In vertical writing modes the block-start is the top, inline-start is the left edge. The name encodes position in flow, not visual position.
- **`float: inline-start` is not supported in Firefox < 131** (as of 2024). Add `@supports (float: inline-start) { ... }` guards and a fallback `float: left` in a `:where([dir="ltr"]) .el { float: left }` block.

---

## Verification

```bash
# 1. Confirm Content-Language header is set for Arabic path
curl -sI https://example.com/ar/home | grep -i content-language
# Content-Language: ar

# 2. Confirm Vary header prevents wrong-locale caching
curl -sI https://example.com/ar/home | grep -i vary
# Vary: Accept-Language

# 3. Confirm no X-Content-Type-Options is missing
curl -sI https://example.com/ | grep -i x-content-type
# X-Content-Type-Options: nosniff

# 4. Visual RTL check with Chrome DevTools
# Open DevTools → Elements → select <html> → inspect dir="rtl" attribute
# Then run in console:
document.documentElement.dir
# "rtl"
```

Automated RTL layout test with Playwright:

```typescript
// tests/rtl.spec.ts
import { test, expect } from '@playwright/test';

test('Arabic home page has dir=rtl', async ({ page }) => {
  await page.goto('/ar/home');
  const dir = await page.evaluate(() => document.documentElement.dir);
  expect(dir).toBe('rtl');
});

test('Navigation links flow from right in Arabic', async ({ page }) => {
  await page.goto('/ar/home');
  const firstLink = page.locator('nav a').first();
  const lastLink  = page.locator('nav a').last();
  const firstBox  = await firstLink.boundingBox();
  const lastBox   = await lastLink.boundingBox();
  // In RTL, first link is on the right; it should have a larger x value
  expect(firstBox!.x).toBeGreaterThan(lastBox!.x);
});
```

---

## Related

- `css-logical-properties-2026.md`
- `rtl-layout-cloudflare-pages-mobile.md`
- `bidi-rtl-layout-css.md`
- `right-to-left-testing-checklist.md`
- `locale-url-routing-workers-middleware.md`
- `arabic-persian-text-rendering.md`

---

## Sources

- [CSS Logical Properties Level 3 – W3C](https://www.w3.org/TR/css-logical-1/)
- [Cloudflare Pages: Headers](https://developers.cloudflare.com/pages/configuration/headers/)
- [MDN: CSS Logical Properties](https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_logical_properties_and_values)
- [Tailwind CSS: Logical Properties](https://tailwindcss.com/docs/margin#using-logical-properties)
- [Unicode BiDi algorithm](https://www.unicode.org/reports/tr9/)
- [Google: Internationalize your app (dir attribute)](https://web.dev/articles/bidi)
