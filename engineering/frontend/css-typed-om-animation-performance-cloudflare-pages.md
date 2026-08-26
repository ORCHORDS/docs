# CSS Typed Object Model — Animation Performance on Cloudflare Pages

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Animating CSS properties with `element.style.transform = 'translateX(100px)'` forces string
parsing on every frame, causing jank on low-end mobile. You want numeric typed values, direct
compositor-friendly mutations, and feature-flag gating via a Cloudflare Worker so only capable
browsers receive the Typed OM code path.

---

## Context

CSS Typed OM (`element.attributeStyleMap` / `CSS.number()` / `CSSUnitValue`) replaces string
serialization with typed JavaScript objects. Mutations bypass the CSS parser, making animation
loops measurably faster. The `@property` rule (Houdini custom properties) integrates with Typed
OM to allow smooth interpolation of custom variables. Cloudflare Pages hosts the SPA; a Worker
injects a `X-Typed-Om-Supported` response header to pre-gate the feature so the client never
needs a runtime check on first paint.

---

## Feature Detection

```typescript
// src/lib/typedOM.ts
export const supportsTypedOM =
  typeof window !== 'undefined' &&
  'attributeStyleMap' in (document.documentElement ?? {});

export const supportsComputedMap =
  typeof window !== 'undefined' &&
  'computedStyleMap' in (document.documentElement ?? {});

/** Read a numeric CSS value from an element without string parsing */
export function getNumericValue(
  el: Element,
  property: string
): number | null {
  if (!supportsComputedMap) return null;
  const map = el.computedStyleMap();
  const val = map.get(property);
  if (val instanceof CSSUnitValue) return val.value;
  return null;
}
```

---

## Typed OM Animation Loop

```typescript
// src/lib/animateWithTypedOM.ts
export function animateSlide(
  el: HTMLElement,
  targetX: number,
  durationMs: number
): void {
  if (!('attributeStyleMap' in el)) {
    // Fallback: classic string style
    el.style.transition = `transform ${durationMs}ms ease`;
    el.style.transform = `translateX(${targetX}px)`;
    return;
  }

  const map = el.attributeStyleMap;
  const start = performance.now();

  // Read current position without triggering layout via string parsing
  const computedMap = el.computedStyleMap();
  const currentTransform = computedMap.get('transform');
  const startX =
    currentTransform instanceof CSSTransformValue
      ? (currentTransform[0] as CSSTranslate).x.value ?? 0
      : 0;

  function tick(now: number) {
    const elapsed = now - start;
    const progress = Math.min(elapsed / durationMs, 1);
    const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
    const current = startX + (targetX - startX) * eased;

    map.set('transform', new CSSTransformValue([
      new CSSTranslate(CSS.px(current), CSS.px(0)),
    ]));

    if (progress < 1) requestAnimationFrame(tick);
  }

  requestAnimationFrame(tick);
}
```

---

## @property + Typed OM for Custom Property Animation

```typescript
// src/lib/registerCustomProperties.ts
/** Register typed custom properties so the browser interpolates them.
 *  Must run before any animation that uses --hue or --progress. */
export function registerCustomProperties(): void {
  if (!('registerProperty' in CSS)) return;

  const defs: PropertyDefinition[] = [
    {
      name: '--hue',
      syntax: '<angle>',
      inherits: false,
      initialValue: '0deg',
    },
    {
      name: '--progress',
      syntax: '<number>',
      inherits: false,
      initialValue: '0',
    },
  ];

  for (const def of defs) {
    try {
      CSS.registerProperty(def);
    } catch {
      // already registered; safe to ignore
    }
  }
}

/** Animate --progress from 0 to 1 using Typed OM writes */
export function animateProgress(
  el: HTMLElement,
  durationMs = 600
): void {
  if (!supportsTypedOM) {
    // CSS transition fallback (requires @property in a stylesheet)
    el.style.setProperty('--progress', '1');
    return;
  }
  const map = el.attributeStyleMap;
  const start = performance.now();

  function tick(now: number) {
    const t = Math.min((now - start) / durationMs, 1);
    map.set('--progress', CSS.number(t));
    if (t < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}
```

---

## Cloudflare Worker — Feature-Flag Header Injection

```typescript
// workers/feature-headers.ts
/**
 * Inject X-Typed-Om-Supported based on UA so the SPA can skip runtime checks
 * and reduce hydration branching.
 */
export default {
  async fetch(req: Request): Promise<Response> {
    const res = await fetch(req);
    const ua = req.headers.get('user-agent') ?? '';

    // Typed OM (attributeStyleMap) available in Chrome 66+, Edge 79+, Safari 16.4+
    // Simple heuristic — tighten with ua-parser in production
    const supported =
      /Chrome\/([7-9]\d|[1-9]\d{2})|Safari\/6[0-9]{2}|Firefox\/\d{3}/.test(ua);

    const headers = new Headers(res.headers);
    headers.set('X-Typed-Om-Supported', supported ? '1' : '0');
    // Vary so CDN caches separate versions
    headers.append('Vary', 'User-Agent');

    return new Response(res.body, {
      status: res.status,
      headers,
    });
  },
};
```

```typescript
// src/bootstrap.ts  (Cloudflare Pages SPA entry point)
import { registerCustomProperties } from './lib/registerCustomProperties';

const typedOMSupported =
  document.documentElement.dataset['typedOm'] === '1' ||
  'attributeStyleMap' in document.documentElement;

if (typedOMSupported) {
  registerCustomProperties();
}
```

---

## Reading Computed Typed Values

```typescript
// src/lib/readComputedStyles.ts
interface TypingResult {
  width: number | null;   // px
  opacity: number | null; // 0–1
  color: [number, number, number] | null; // rgb
}

export function readComputedStyles(el: Element): TypingResult {
  if (!supportsComputedMap) {
    return { width: null, opacity: null, color: null };
  }

  const map = el.computedStyleMap();

  const widthVal = map.get('width');
  const width = widthVal instanceof CSSUnitValue
    ? widthVal.to('px').value
    : null;

  const opacityVal = map.get('opacity');
  const opacity = opacityVal instanceof CSSUnitValue
    ? opacityVal.value
    : null;

  // Color is returned as CSSStyleValue — parse from string fallback if needed
  const colorVal = map.get('color');
  const color: [number, number, number] | null =
    colorVal instanceof CSSColorValue
      ? [colorVal.channels[0], colorVal.channels[1], colorVal.channels[2]]
      : null;

  return { width, opacity, color };
}
```

---

## Anti-patterns

- **Mixing `element.style` writes with `attributeStyleMap.set()`** — they compete; pick one API per property per element.
- **Using Typed OM for non-animating styles** — the overhead of creating `CSSUnitValue` objects is only worth it inside `requestAnimationFrame` loops with > 60 property mutations per second.
- **Registering `@property` inside a loop** — `CSS.registerProperty` throws if called twice with the same name; wrap in try/catch or guard with a `Set`.
- **Assuming `CSSTransformValue` is indexable** — iterate with `for...of` or access `[Symbol.iterator]`; numeric index access is not guaranteed across browser versions.
- **Gating on UA string alone** — always include a runtime `'attributeStyleMap' in el` guard as the final check.

---

## Gotchas

- `CSSColorValue` is not yet available in all browsers (Firefox ships it behind a flag as of 2026); always fallback to `getComputedStyle(el).color`.
- `CSS.px(n)` returns a new object on each call — cache values when animating to avoid GC pressure in tight loops.
- `attributeStyleMap.set()` applies inline styles; these have higher specificity than class-based animations and may override design tokens.
- In Cloudflare Workers, `CSS` is **not** available — the Typed OM is a browser-only API. Never import Typed OM utilities into a Worker bundle.
- `computedStyleMap()` forces a style resolution (but not a layout), so avoid calling it inside a `requestAnimationFrame` before reads are done.

---

## Verification

```typescript
// src/lib/__tests__/typedOM.test.ts
import { describe, it, expect, vi } from 'vitest';

describe('getNumericValue', () => {
  it('returns null when computedStyleMap is absent', () => {
    const el = document.createElement('div');
    // jsdom lacks computedStyleMap
    const { getNumericValue } = await import('../typedOM');
    expect(getNumericValue(el, 'width')).toBeNull();
  });
});

// Manual smoke test in browser console:
// const el = document.querySelector('.card');
// el.attributeStyleMap.set('opacity', CSS.number(0.5));
// el.computedStyleMap().get('opacity').value  // → 0.5
```

```bash
# Lighthouse check: ensure no layout thrashing from Typed OM animation
npx lighthouse https://pages.example.com/animate --only-categories=performance \
  --output=json | jq '.audits["layout-shift"].score'
# expect: 1 (no CLS from animation)
```

---

## Related

- `registered-css-custom-properties-at-property.md`
- `css-houdini-paint-api-cloudflare-pages.md`
- `css-animation-performance.md`
- `web-animations-api-workers-performance.md`
- `scheduler-api-cooperative-multitasking-workers-performance.md`

---

## Sources

- https://developer.mozilla.org/en-US/docs/Web/API/CSS_Typed_OM_API
- https://developer.chrome.com/docs/css-ui/cssom
- https://drafts.css-houdini.org/css-typed-om/
- https://developers.cloudflare.com/pages/
- https://developers.cloudflare.com/workers/runtime-apis/response/
