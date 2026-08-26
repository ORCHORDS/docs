# CSS Masonry Layout with Progressive Enhancement on Cloudflare Pages

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Pinterest-style card grids (variable-height items packed into columns) traditionally
require JavaScript: measure each card's height, calculate column assignments, and
re-run on resize. This approach causes layout thrash, blocks the main thread, and
produces cumulative layout shift (CLS) while heights are being measured. CSS Masonry
— specified as `grid-template-rows: masonry` (or `grid-template-columns: masonry`)
— delegates column packing to the browser's layout engine, eliminating JS-driven
reflows entirely. The feature shipped behind a flag in Firefox 77+ and Chrome 132+
(Intent to Ship filed 2025) and is approaching cross-browser baseline. A
`@supports` progressive-enhancement strategy keeps the layout functional on all
browsers today.

---

## Context

CSS Masonry is part of the CSS Grid Level 3 specification. The grid axis retains
normal track sizing while the masonry axis packs items greedily into the smallest
available gap. Two syntaxes exist in the spec:

```css
/* Items flow in columns, masonry axis is rows */
.grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  grid-template-rows: masonry;   /* masonry on the block axis */
}

/* Items flow in rows, masonry axis is columns (less common) */
.grid {
  display: grid;
  grid-template-rows: repeat(3, auto);
  grid-template-columns: masonry;
}
```

Chrome 132+ also supports `masonry` as a value for the shorthand:

```css
.grid {
  display: masonry;   /* Chrome 132+ alternative syntax — avoid for now */
}
```

Stick with the `grid-template-rows/columns: masonry` form; the `display: masonry`
shorthand is still in flux.

---

## Progressive Enhancement Strategy

Wrap masonry-specific declarations in `@supports` so unsupported browsers fall back
to a clean multi-column layout:

```css
/* _masonry.css */

/* Fallback: CSS columns (all browsers) */
.card-grid {
  column-count: 1;
  column-gap: 1rem;
}

@media (min-width: 640px)  { .card-grid { column-count: 2; } }
@media (min-width: 1024px) { .card-grid { column-count: 3; } }
@media (min-width: 1280px) { .card-grid { column-count: 4; } }

.card-grid > * {
  break-inside: avoid;          /* prevent cards splitting across columns */
  margin-bottom: 1rem;
  display: inline-block;        /* required for column flow */
  width: 100%;
}

/* Enhancement: native masonry where supported */
@supports (grid-template-rows: masonry) {
  .card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    grid-template-rows: masonry;
    gap: 1rem;
    /* Reset column-count so the two layouts don't fight */
    column-count: unset;
    column-gap: unset;
  }

  .card-grid > * {
    break-inside: unset;
    margin-bottom: unset;
    display: block;
    width: unset;
  }
}
```

---

## React Component Wrapper

```tsx
// src/components/MasonryGrid.tsx
import type { ReactNode, CSSProperties } from 'react';

interface MasonryGridProps {
  children: ReactNode;
  minColumnWidth?: number;   // px, default 280
  gap?: string;              // CSS length, default '1rem'
  fallbackColumns?: number;  // column-count when masonry unsupported, default 3
}

export function MasonryGrid({
  children,
  minColumnWidth = 280,
  gap = '1rem',
  fallbackColumns = 3,
}: MasonryGridProps) {
  const style: CSSProperties = {
    // Fallback values applied unconditionally — @supports overrides in CSS
    columnCount: fallbackColumns,
    columnGap: gap,
  };

  return (
    <div className="masonry-grid" style={style} data-min-col={minColumnWidth}>
      {children}
    </div>
  );
}
```

```css
/* src/components/MasonryGrid.module.css */
.masonry-grid > * {
  break-inside: avoid;
  margin-bottom: var(--masonry-gap, 1rem);
  display: inline-block;
  width: 100%;
}

@supports (grid-template-rows: masonry) {
  .masonry-grid {
    display: grid;
    grid-template-columns: repeat(
      auto-fill,
      minmax(var(--masonry-min-col, 280px), 1fr)
    );
    grid-template-rows: masonry;
    gap: var(--masonry-gap, 1rem);
    column-count: unset !important;
  }

  .masonry-grid > * {
    break-inside: unset;
    margin-bottom: unset;
    display: block;
    width: unset;
  }
}
```

---

## JavaScript Fallback with ResizeObserver (for Browsers Without Masonry)

When the `@supports` block is absent and CSS columns produce unacceptable visual
results (e.g., items must appear in row order rather than column order), use a
lightweight JS masonry:

```typescript
// src/lib/js-masonry.ts
export function initJsMasonry(container: HTMLElement): () => void {
  if (CSS.supports('grid-template-rows', 'masonry')) {
    return () => {}; // native masonry active; no-op cleanup
  }

  const reflow = () => {
    const columnCount = parseInt(
      getComputedStyle(container).columnCount ?? '1',
      10
    );
    if (columnCount <= 1) return;

    const items = Array.from(container.children) as HTMLElement[];
    const columns: number[] = Array(columnCount).fill(0);
    const gap = parseFloat(getComputedStyle(container).columnGap) || 16;

    container.style.position = 'relative';
    const colWidth =
      (container.clientWidth - gap * (columnCount - 1)) / columnCount;

    items.forEach((item) => {
      item.style.position = 'absolute';
      item.style.width = `${colWidth}px`;

      const shortestCol = columns.indexOf(Math.min(...columns));
      item.style.left = `${shortestCol * (colWidth + gap)}px`;
      item.style.top = `${columns[shortestCol]}px`;

      columns[shortestCol] += item.offsetHeight + gap;
    });

    container.style.height = `${Math.max(...columns)}px`;
  };

  const ro = new ResizeObserver(reflow);
  ro.observe(container);
  reflow();

  return () => ro.disconnect();
}
```

---

## Cloudflare Pages Build Integration

No special Pages configuration is needed. The CSS above is purely client-rendered.
For SSR (Astro, Remix, SvelteKit on Pages), render the grid HTML server-side and
rely on `@supports` to apply the correct layout without hydration:

```astro
---
// src/pages/gallery.astro
import { MasonryGrid } from '../components/MasonryGrid';
import { Card } from '../components/Card';
import { getImages } from '../lib/r2-images';

const images = await getImages();   // fetched from R2 via Worker binding
---

<section class="masonry-grid">
  {images.map((img) => (
    <Card key={img.id} src={img.url} alt={img.alt} />
  ))}
</section>
```

Because the layout is CSS-only in supporting browsers, there is zero CLS from
masonry reflow — the browser's layout pass handles packing before first paint.

---

## Responsive Column Count

Combine `auto-fill` with `minmax` for fully fluid column counts, or use explicit
`@media` breakpoints for predictability:

```css
@supports (grid-template-rows: masonry) {
  .masonry-grid {
    grid-template-columns:
      repeat(auto-fill, minmax(clamp(220px, 30vw, 400px), 1fr));
    grid-template-rows: masonry;
  }
}
```

`clamp()` prevents columns from ever being narrower than 220 px or wider than 400 px,
regardless of viewport width, without any JS or media query duplication.

---

## Anti-patterns

- **Testing only in Chrome**: Chrome 132+ supports masonry but the spec syntax
  changed between versions. Always test the `@supports` fallback in Firefox ESR
  and Safari 17 to confirm the column fallback renders acceptably.
- **Setting `align-items: stretch` on the masonry axis**: Masonry items are sized
  by their content on the masonry axis. Overriding this with `stretch` breaks
  the height packing algorithm.
- **Using `display: masonry`**: The shorthand syntax is experimental and not in
  the `@supports` detection path consistently across browsers. Use
  `grid-template-rows: masonry` for reliable feature detection.
- **Animating `grid-template-rows`**: Masonry track sizing is not animatable.
  Animate individual card transforms instead.

---

## Gotchas

- `@supports (grid-template-rows: masonry)` returns `false` in Chrome versions
  prior to 132, even though those versions have partial masonry behind a flag.
  This is the correct behaviour — flag-gated features should not affect
  production `@supports` detection.
- CSS Masonry does not support `grid-auto-flow: dense`. The dense packing
  algorithm is explicitly excluded from the masonry specification.
- Items placed with explicit `grid-row` or `grid-column` values are removed
  from the masonry flow. Avoid explicit placement on masonry-axis tracks.
- The JS fallback uses `position: absolute` which removes items from normal
  flow. Ensure the fallback is activated only when CSS masonry is absent.

---

## Verification

1. Open the page in Chrome 132+ — verify the layout uses native masonry by
   inspecting the computed styles for `grid-template-rows: masonry`.
2. In Chrome DevTools, toggle **Rendering → Emulate CSS media feature:
   forced-colors** and confirm the fallback columns render.
3. Disable the `@supports` block temporarily and verify the `column-count`
   fallback produces a readable layout.
4. Run Lighthouse; CLS should be 0 for the masonry grid (no JS reflow).

---

## Related

- `css-grid-layouts.md` — CSS Grid fundamentals
- `css-container-queries.md` — responsive sizing without media queries
- `css-scroll-driven-animations.md` — animating card entry on scroll
- `intersection-observer-lazy-load-r2.md` — lazy loading masonry card images

---

## Sources

- CSS Grid Level 3 (Masonry) spec: https://drafts.csswg.org/css-grid-3/
- Chrome Intent to Ship: https://groups.google.com/a/chromium.org/g/blink-dev/c/
- MDN Masonry Layout: https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_grid_layout/Masonry_layout
- Cloudflare Pages build docs: https://developers.cloudflare.com/pages/framework-guides/
