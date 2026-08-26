# CSS Container Queries and :has() Selector — Component-Level Responsive Design

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your card component uses media queries to switch between stacked and
horizontal layouts. It looks correct in the main content area, but
when the same card renders in a narrow sidebar, the media query still
triggers the wide layout because the viewport is wide — only the
container is narrow. You add a `.sidebar .card` override, then a
`.modal .card` override, then a `.drawer .card` override, creating
a cascade of context-specific CSS that breaks every time the card
appears in a new container.

## Context

CSS Container Queries (baseline since February 2023) let components
respond to their container's size rather than the viewport's size.
The `:has()` selector (supported in all major browsers, 93%+ global
coverage in 2026) enables parent selection — styling elements based
on what they contain. Together, these two features eliminate the
majority of context-specific layout overrides and JavaScript-based
responsive logic. Container queries are complementary to media queries:
use container queries for component-level responsiveness, media queries
for viewport-level layout and user preference detection.

## Container query setup

```css
/* Longhand */
.card-wrapper {
  container-type: inline-size;
  container-name: card;
}

/* Shorthand: name / type */
.card-wrapper {
  container: card / inline-size;
}

/* Query the container */
@container card (min-width: 400px) {
  .card-body {
    flex-direction: row;
  }
}

/* Range syntax (CSS Media Queries Level 4) */
@container card (350px <= width < 500px) {
  h2 { font-size: 1.5rem; }
}

/* Logical conditions */
@container (width >= 350px) and (width < 500px) { /* ... */ }
@container not (width < 200px) { /* ... */ }
```

## Container types

```
container-type values:

  inline-size   Query inline axis only (width in horizontal mode)
                Use 90% of the time — the safe default

  size          Query both inline and block axes
                Rarely needed — adds block containment that can
                collapse elements with intrinsic heights

  normal        Not a size query container (default)
                Still a style query container
```

## Container query units

```css
/* Six units relative to the query container, not the viewport */
.profile {
  padding: clamp(0.5rem, 10cqi, 1.5rem);
}
.profile .name {
  font-size: clamp(14px, 10px + 1.33cqi, 20px);
}
```

```
Unit    Meaning
cqw     1% of container width
cqh     1% of container height
cqi     1% of container inline size (prefer over cqw)
cqb     1% of container block size (prefer over cqh)
cqmin   Smaller of cqi or cqb
cqmax   Larger of cqi or cqb

Note: container query units cannot size the container itself —
only its descendants.
```

## Style container queries

```css
/* Style queries work on custom properties only (2026) */
/* No container-type needed — every element is a style container */

/* Boolean check */
@container style(--theme-color) {
  .text { color: var(--theme-color); }
}

/* Value match */
@container style(--layout: grid) {
  .content {
    display: grid;
    grid-template-columns: 1fr 1fr;
  }
}

/* Combine size and style queries */
@container (min-width: 300px) and style(--variant: featured) {
  .card { border: 2px solid gold; }
}
```

## :has() selector

```css
/* Style parent based on what it contains */
.card:has(img) {
  display: grid;
  grid-template-rows: 200px 1fr;
}
.card:not(:has(img)) {
  padding: 2rem;
}

/* Adjacent sibling — "previous sibling" selector (new capability) */
h2:has(+ p) {
  margin-bottom: 0.5rem;
}

/* Form validation without JavaScript */
.form-group:has(> input:invalid:not(:placeholder-shown)) {
  border-color: red;
}

/* Quantity queries — adapt layout by child count */
.grid:has(:nth-child(4)) {
  grid-template-columns: repeat(2, 1fr);
}
.grid:has(:nth-child(7)) {
  grid-template-columns: repeat(3, 1fr);
}
```

## Browser support (2026)

```
Feature                              Status
───────────────────────────────────────────────────────
Size container queries               Baseline (Feb 2023), all browsers
Container query units                Fully supported everywhere
Style queries (custom properties)    Chrome, Edge, Safari; awaiting Firefox
Style queries (computed properties)  Not implemented in any browser
Scroll-state container queries       Chrome, Edge, Opera only
:has() selector                      93%+ global support, all major browsers
```

## Anti-patterns

- **Using `container-type: size` when `inline-size` suffices** — `size`
  adds block-axis containment that can collapse elements with intrinsic
  heights. Default to `inline-size`.
- **Forgetting to name containers** — without names, `@container`
  resolves to the nearest ancestor container. In nested component
  trees, inner components accidentally match outer containers.
- **Using media queries for component responsiveness** — components
  should respond to their container, not the viewport. Media queries
  remain correct for viewport layout and user preference detection.
- **`body:has()` for frequently changing states** — `body:has(input:focus)`
  triggers full-document recalculation on every focus event. Scope
  `:has()` to component-level selectors.

## Gotchas

- **A container cannot query itself** — you must measure an ancestor.
  This sometimes forces adding a wrapper element.
- **Flexbox items as containers without explicit sizing** — the
  container's measured size can collapse to zero when no width
  constraint exists, causing queries to never match.
- **`var()` inside query conditions is invalid** — you cannot write
  `@container (min-width: var(--bp))`. Container query breakpoints
  must be static values.
- **`:has()` specificity** — `:has()` itself contributes zero, but
  selectors inside it count. `.card:has(.featured)` = (0,2,0). Wrap
  in `:where()` to zero it out: `.card:has(:where(.featured))`.
- **`:has()` cannot nest** — `:has(:has(...))` is invalid. Also cannot
  cross shadow DOM boundaries or match pseudo-elements.
- **Style query recomputation** — Chrome's May 2026 notes report
  frequent style query recomputation can add 4-7ms to INP on long
  lists.

## Verification

- Components use container queries instead of context-specific CSS overrides.
- Container type is `inline-size` unless block-axis queries are needed.
- All containers are named in nested component hierarchies.
- `:has()` selectors are scoped to component level, not `body`/`html`.
- Media queries are reserved for viewport layout and user preferences.
- Wrapper elements exist where containers need to query parent size.

## Related

- `documentation/docs/policies/frontend/view-transitions-api-page-navigation.md`
- `documentation/docs/policies/performance/critical-rendering-path-css-optimization.md`
- `documentation/docs/policies/performance/web-workers-sharedarraybuffer-parallelism.md`

## Source URLs (verified 2026-08-16)

- Container Queries in 2026: Powerful but Not a Silver Bullet — https://blog.logrocket.com/container-queries-2026/
- CSS :has() Selector: Complete Parent Selector Guide (2026) — https://cssawwwards.com/blog/css-has-selector-guide-2026
- The Ultimate Guide to CSS Container Queries in 2026 — https://dev.to/nickbenksim/the-ultimate-guide-to-css-container-queries-in-2026-1ndi
- Using Container Size and Style Queries — MDN — https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Containment/Container_size_and_style_queries
