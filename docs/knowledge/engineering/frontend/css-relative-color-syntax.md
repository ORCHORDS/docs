# CSS Relative Color Syntax — Dynamic Theming

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case
You need to derive tints, shades, and accessible contrast variants from a single brand token at authoring time — without a preprocessor, a JS color library, or duplicate hex values scattered across a stylesheet.

## Context
CSS relative color syntax (`oklch(from var(--brand) l c h)`) lets you take any color and produce a mathematically transformed variant inline in CSS. Combined with `@property` typed custom properties and the `color-mix()` function, it enables a full design-token palette from one source of truth. Because it is pure CSS evaluated by the browser, it works identically whether pages are served from Cloudflare Pages static assets or edge-rendered Workers responses — no build-time compilation required.

## Baseline and Feature Detection

```css
/* globals.css */

/* Opt-in gate — browsers that don't support relative colors get the fallback tokens */
@supports (color: oklch(from red l c h)) {
  :root {
    --supports-relative-color: 1;
  }
}

:root {
  /* Source of truth — one brand hue */
  --brand-oklch: oklch(55% 0.22 265);   /* vivid indigo */

  /* Static fallbacks for non-supporting browsers */
  --color-primary:         #3b5bdb;
  --color-primary-light:   #748ffc;
  --color-primary-dark:    #1c3faa;
  --color-primary-surface: #edf2ff;
  --color-on-primary:      #ffffff;
}

/* Override with computed variants once relative color is available */
@supports (color: oklch(from red l c h)) {
  :root {
    --color-primary:         var(--brand-oklch);
    --color-primary-light:   oklch(from var(--brand-oklch) calc(l + 0.2) c h);
    --color-primary-dark:    oklch(from var(--brand-oklch) calc(l - 0.15) c h);
    --color-primary-surface: oklch(from var(--brand-oklch) 0.96 calc(c * 0.15) h);
    /* Derived on-color: keep hue, push lightness to near-white */
    --color-on-primary:      oklch(from var(--brand-oklch) 0.98 0.01 h);
  }
}
```

## Typed @property Registration

```css
/* Register typed custom properties so the browser can interpolate them */
@property --brand-oklch {
  syntax: '<color>';
  inherits: true;
  initial-value: oklch(55% 0.22 265);
}

@property --color-primary {
  syntax: '<color>';
  inherits: true;
  initial-value: #3b5bdb;
}

@property --color-primary-light {
  syntax: '<color>';
  inherits: true;
  initial-value: #748ffc;
}

/* Smooth theme transitions become possible once the type is '<color>' */
:root {
  transition:
    --color-primary 300ms ease,
    --color-primary-light 300ms ease,
    --color-primary-dark 300ms ease,
    --color-primary-surface 300ms ease;
}
```

## Dynamic Brand Switching at Runtime

```ts
// src/theme.ts — called when user picks a brand color in a settings panel
export function applyBrandColor(hslHex: string) {
  // CSS.registerProperty is already done via @property in the stylesheet
  document.documentElement.style.setProperty('--brand-oklch', hslHex)
  // All derived --color-primary-* tokens recompute automatically
}

// Persist selection across page loads via Cloudflare Pages KV (edge-side) or localStorage
export async function persistBrandColor(color: string) {
  localStorage.setItem('brand-color', color)
  // Optionally write to KV through a Pages Function for cross-device sync
  await fetch('/api/preferences', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ brandColor: color }),
  })
}

export function restoreBrandColor() {
  const saved = localStorage.getItem('brand-color')
  if (saved) applyBrandColor(saved)
}
```

## Contrast Checking Variant

```css
/* Accessible foreground derived from background using relative color */
:root {
  --surface-bg: oklch(98% 0.01 265);

  /* Flip lightness to opposite pole, preserve hue — crude but effective */
  --surface-fg: oklch(from var(--surface-bg) calc(1 - l) c h);
}

/* More precise: push fg to near-black in light contexts */
@supports (color: oklch(from red l c h)) {
  :root {
    /* clamp keeps lightness in a readable range regardless of source */
    --surface-fg: oklch(
      from var(--surface-bg)
      clamp(0.05, calc(1 - l), 0.2)
      calc(c * 0.3)
      h
    );
  }
}

/* Semantic alert colors derived from the same hue wheel offsets */
:root {
  --color-success:  oklch(from var(--brand-oklch) 0.58 0.18 145);   /* hue 145 = green */
  --color-warning:  oklch(from var(--brand-oklch) 0.72 0.17  85);   /* hue  85 = yellow */
  --color-danger:   oklch(from var(--brand-oklch) 0.52 0.22  25);   /* hue  25 = red   */
}
```

## Anti-patterns
- Mixing `oklch()` relative syntax with `hsl()` source tokens — channel names differ (`l`, `c`, `h` vs `h`, `s`, `l`); use one color space consistently
- Using `rgb(from ...)` and expecting hue manipulation — the RGB channels do not correspond to perceptual attributes; use `oklch` for lightness/chroma work
- Registering `@property` with `syntax: '<custom-ident>'` instead of `'<color>'` — the browser will not interpolate or compute the derived tokens correctly
- Omitting the static fallback block — browsers without `@supports` will receive `initial-value` only if `@property` is registered, otherwise no color at all
- Putting very large `calc()` expressions inside `oklch(from ...)` — the browser evaluates these per element; prefer computing on `:root` and inheriting

## Gotchas
- `oklch(from var(--x) l c h)` is equivalent to `var(--x)` — relative color only becomes useful when you actually modify at least one channel
- The `none` keyword is contagious: if the source color's hue is `none` (achromatic), `h` resolves to `0deg`; guard with `color-mix()` when the source may be grey
- Cloudflare's HTML rewriter does not parse CSS — it operates on HTML tokens; injecting a brand color via a `<style>` tag in a Worker response is safe
- Chrome 119+, Safari 17.5+, Firefox 128+ support relative color syntax; Edge follows Chrome; check caniuse.com before skipping the `@supports` guard
- `transition` on `@property` typed tokens works, but animating `--brand-oklch` directly triggers a full cascade recalc each frame — prefer animating a single composite property instead

## Verification

```html
<!-- Quick browser test page -->
<!doctype html>
<html>
<head>
  <style>
    @property --brand-oklch { syntax: '<color>'; inherits: true; initial-value: oklch(55% 0.22 265); }
    :root { --derived: oklch(from var(--brand-oklch) calc(l + 0.2) c h); }
    body { background: var(--derived); min-height: 100vh; }
  </style>
</head>
<body></body>
</html>
```

```bash
# Verify CSS is served correctly from Pages
curl -I https://my-pages-project.pages.dev/globals.css \
  | grep -i 'content-type'
# → content-type: text/css; charset=utf-8

# Check browser support matrix
npx browserslist "last 2 Chrome versions, last 2 Safari versions, last 2 Firefox versions"
```

## Related
- [css-custom-properties-theming.md](css-custom-properties-theming.md)
- [registered-css-custom-properties-at-property.md](registered-css-custom-properties-at-property.md)
- [dark-mode-css-custom-properties-cloudflare-edge-detection.md](dark-mode-css-custom-properties-cloudflare-edge-detection.md)
- [css-light-dark-system-color-contract.md](css-light-dark-system-color-contract.md)
- [design-token-pipelines.md](design-token-pipelines.md)

## Sources
- https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_colors/Relative_colors
- https://www.w3.org/TR/css-color-5/#relative-colors
- https://oklch.com/
- https://caniuse.com/css-relative-colors
