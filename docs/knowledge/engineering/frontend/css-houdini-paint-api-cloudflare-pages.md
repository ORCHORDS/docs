# CSS Houdini Paint API — Custom Worklets on Cloudflare Pages

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You want a fully custom CSS background or border effect — animated noise, procedural
gradients, ripple borders — without baking the visual into a PNG or running a Canvas
loop. CSS Houdini's Paint API lets you register a `paint()` worklet that the browser
calls at layout time, giving you a `CanvasRenderingContext2D`-like API with access to
the element's computed size and custom CSS properties.

## Context

The CSS Painting API (Houdini) is supported in Chrome/Edge 65+ and Opera. Firefox and
Safari ship it behind flags (2026-08). The worklet script must be loaded via
`CSS.paintWorklet.addModule(url)` before any element tries to use `paint(name)` in CSS.

On Cloudflare Pages the worklet file is a static asset served like any other JS file.
No Workers or special edge logic is required unless you want to dynamically generate the
worklet at the edge (rare). The main gotcha is that paint worklets run in a separate
global (no `window`, no `fetch`, no ES modules) and must be plain classic scripts.

## Writing a Paint Worklet

The worklet file must be a **classic script** (no `import`/`export`). Register input
properties and your painter class:

```javascript
// public/worklets/noise-border.js  (classic script — no ES module syntax)
registerPaint('noise-border', class {
  static get inputProperties() {
    // Custom CSS properties the worklet reads
    return ['--noise-frequency', '--noise-color', '--border-width'];
  }

  static get contextOptions() {
    return { alpha: true };
  }

  paint(ctx, geom, props) {
    const freq = parseFloat(props.get('--noise-frequency').toString()) || 0.8;
    const color = props.get('--noise-color').toString().trim() || '#6366f1';
    const bw = parseInt(props.get('--border-width').toString()) || 4;

    const { width, height } = geom;

    // Draw a noisy border by sampling pseudo-random values
    ctx.strokeStyle = color;
    ctx.lineWidth = bw;

    ctx.beginPath();
    for (let x = 0; x <= width; x += 2) {
      const jitter = (Math.sin(x * freq + Date.now() * 0.001) * bw) / 2;
      x === 0 ? ctx.moveTo(x, jitter) : ctx.lineTo(x, jitter);
    }
    // Right edge, bottom edge, left edge (simplified)
    ctx.lineTo(width, height);
    ctx.lineTo(0, height);
    ctx.closePath();
    ctx.stroke();
  }
});
```

Note: `Date.now()` inside `paint()` does **not** cause automatic re-paint. To animate
you must invalidate via a CSS custom property change (e.g., toggle a `--tick` value from
JS with `requestAnimationFrame`).

## Registering the Worklet in the App

```typescript
// lib/houdini.ts
let registered = false;

export async function registerPaintWorklets(): Promise<void> {
  if (registered || typeof CSS === 'undefined' || !('paintWorklet' in CSS)) return;
  registered = true;

  // Cloudflare Pages serves the worklet from /worklets/
  await (CSS as any).paintWorklet.addModule('/worklets/noise-border.js');
}
```

Call this once at app startup (after hydration in SSR frameworks):

```typescript
// app/entry.client.tsx  (Remix / React Router v7)
import { registerPaintWorklets } from '../lib/houdini';
import { hydrateRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';

registerPaintWorklets(); // fire and forget — non-blocking
hydrateRoot(document, <RouterProvider router={router} />);
```

## Registering Custom CSS Properties (CSS.registerProperty)

Houdini painted values react to CSS transitions only if the property is typed. Register
each custom property used by the worklet:

```typescript
// lib/houdini.ts  (continued)
export function registerCustomProperties(): void {
  if (typeof CSS === 'undefined' || !('registerProperty' in CSS)) return;

  const defs = [
    { name: '--noise-frequency', syntax: '<number>', inherits: false, initialValue: '0.8' },
    { name: '--noise-color',     syntax: '<color>',  inherits: true,  initialValue: '#6366f1' },
    { name: '--border-width',    syntax: '<integer>', inherits: false, initialValue: '4' },
  ] as const;

  for (const def of defs) {
    try {
      (CSS as any).registerProperty(def);
    } catch {
      // Already registered — safe to ignore
    }
  }
}
```

Without `registerProperty`, CSS transitions on those properties are ignored and the
worklet receives opaque string values only.

## Using the Worklet in CSS

```css
/* styles/components/card.css */
@supports (background: paint(noise-border)) {
  .card--houdini {
    --noise-frequency: 1.2;
    --noise-color: #6366f1;
    --border-width: 3;

    background: paint(noise-border);
    border: none; /* worklet draws the border */
    transition: --noise-frequency 0.3s ease;
  }

  .card--houdini:hover {
    --noise-frequency: 2.5;
  }
}

/* Fallback for unsupported browsers */
.card--houdini {
  border: 3px solid #6366f1;
}
```

`@supports (background: paint(name))` is the correct feature-query. It returns `false`
in Firefox/Safari, so the fallback border applies there.

## Cloudflare Pages Deployment Notes

The worklet JS file must be in your `public/` (or `dist/`) output directory. Configure
Vite to copy it without transformation — classic scripts break if processed by Vite's
ESM transform:

```typescript
// vite.config.ts
import { defineConfig } from 'vite';
import { viteStaticCopy } from 'vite-plugin-static-copy';

export default defineConfig({
  plugins: [
    viteStaticCopy({
      targets: [
        { src: 'src/worklets/*', dest: 'worklets' },
      ],
    }),
  ],
});
```

Add cache headers in `public/_headers`:

```
/worklets/*
  Cache-Control: public, max-age=31536000, immutable
  Content-Type: application/javascript
```

The `Content-Type: application/javascript` header is required — some Cloudflare Pages
edge nodes may serve `.js` files without a MIME type if the file was not in the original
Cloudflare Pages asset manifest.

## Anti-patterns

- **Using ES module syntax in the worklet.** `import` throws a `SyntaxError` because
  paint worklets run as classic workers. Bundle any dependencies inline with a simple
  IIFE or write them inline.
- **Calling `CSS.paintWorklet.addModule` in a component.** Each call re-parses the
  script. Call it once at the application root.
- **Animating via `setInterval` inside `paint()`.** The worklet has no access to
  `setTimeout`/`setInterval`. Drive animation from the main thread via CSS or a
  `requestAnimationFrame` loop that updates a registered custom property.
- **Forgetting `@supports`.** Without the guard, `background: paint(name)` is treated as
  `background: none` on unsupported browsers and the element loses its fallback style.

## Gotchas

- The worklet origin must match the page origin (same-origin restriction). Cannot load
  from a CDN without setting `crossOrigin` first — and even then Chromium restricts it.
- `inputProperties` must list every CSS property the worklet reads. Unlisted properties
  return empty strings inside `paint()`.
- Re-registering the same worklet name does not throw but silently no-ops in Chrome;
  refreshes require a hard reload during development.
- SSR / Node: `CSS.paintWorklet` does not exist in Node. The `registerPaintWorklets()`
  call must be guarded with `typeof window !== 'undefined'` or deferred to
  `entry.client`.

## Verification

1. Open Chrome DevTools → Sources → Worklets. The `noise-border.js` file should appear
   under "Paint Worklets".
2. Inspect the `.card--houdini` element; computed `background` should read `paint(noise-border)`.
3. Toggle `--noise-frequency` in the Styles pane; the border redraws immediately.
4. Open Firefox; verify the fallback `border: 3px solid` renders instead.
5. Run Lighthouse — Houdini backgrounds are GPU-accelerated and should not regress INP
   or CLS scores.

## Related

- `registered-css-custom-properties-at-property.md`
- `css-animation-performance.md`
- `css-custom-properties-theming.md`
- `vite-plugin-development.md`
- `cloudflare-pages-headers-csp-mobile.md`

## Sources

- https://developer.chrome.com/docs/css-ui/houdini-paint
- https://houdini.how/
- https://www.w3.org/TR/css-paint-api-1/
- https://developer.mozilla.org/en-US/docs/Web/API/CSS_Painting_API
- https://developers.cloudflare.com/pages/configuration/headers/
