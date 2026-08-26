# RTL CSS Layout Patterns

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A UI built for LTR breaks when `dir="rtl"` is applied:
padding appears on the wrong side, icons point the wrong way,
left-anchored dropdowns obscure content, and Flexbox rows do
not reverse as expected.

## Context

RTL support touches CSS layout, icon assets, component logic,
and test strategy. Arabic, Hebrew, Persian, and Urdu together
represent over 400 million native speakers. Adding RTL from
the start costs far less than retrofitting it later. The most
reliable approach combines the HTML `dir` attribute, CSS
logical properties, and automated visual-regression snapshots
that catch mirroring regressions without requiring a native
RTL speaker on the engineering team.

## 1. The `dir` attribute and the `direction` property

Set direction once on `<html>`, not on individual components.
The attribute propagates through the DOM automatically.

```html
<!-- Correct: set once on the root -->
<html lang="ar" dir="rtl">
  <body>…</body>
</html>
```

The CSS `direction` property mirrors the attribute but does
not engage the Unicode Bidirectional Algorithm for inline
text — prefer the HTML attribute for layout control and
reserve `direction` for narrow programmatic overrides.

```css
/* Only when the dir attribute cannot be set in markup */
.force-rtl { direction: rtl; }
```

## 2. Logical properties vs physical properties

Physical properties (`margin-left`, `padding-right`) are
fixed to screen coordinates and break in RTL. Logical
properties flip automatically with the writing direction.

| Physical           | Logical equivalent       |
|--------------------|--------------------------|
| `margin-left`      | `margin-inline-start`    |
| `margin-right`     | `margin-inline-end`      |
| `padding-left`     | `padding-inline-start`   |
| `padding-right`    | `padding-inline-end`     |
| `border-left`      | `border-inline-start`    |
| `left` (positioned)| `inset-inline-start`     |
| `right` (positioned)| `inset-inline-end`      |

```css
/* Before — breaks in RTL */
.card { margin-left: 1rem; padding-right: 0.5rem; }

/* After — works in LTR and RTL */
.card {
  margin-inline-start: 1rem;
  padding-inline-end: 0.5rem;
}
```

Block-direction properties (`margin-top`, `margin-bottom`,
`inset-block-start`) are unaffected by RTL; only the
inline axis needs migration.

## 3. Tailwind RTL support

Tailwind v3.3+ ships logical-property utilities directly.
Prefer them over the `rtl:` variant — they require no
conditional logic and produce fewer class names.

```html
<!-- Old approach with rtl: variant -->
<div class="ml-4 rtl:ml-0 rtl:mr-4">…</div>

<!-- Preferred: logical utilities always correct -->
<div class="ms-4">…</div>  <!-- margin-inline-start -->
<div class="pe-2">…</div>  <!-- padding-inline-end   -->
```

The `rtl:` variant is still useful when the logical-
property utility does not exist (e.g. `rtl:text-right`
for alignment, until `text-start` is available).

## 4. `writing-mode` and vertical scripts

`writing-mode` controls whether text flows horizontally
or vertically. It is separate from RTL and targets CJK
typesetting, not Arabic or Hebrew.

```css
/* Arabic / Hebrew — horizontal, right-to-left */
html[dir="rtl"] { writing-mode: horizontal-tb; }

/* Japanese tategumi — vertical, right-to-left */
.jp-vertical { writing-mode: vertical-rl; }
```

Do not use `writing-mode: vertical-*` to implement RTL
for Semitic scripts; they are always horizontal-tb.

## 5. Icon mirroring rules

Directional icons (arrows, chevrons, progress bars,
pagination controls) must mirror in RTL. Semantic or
non-directional icons must not.

```css
/* Mirror a directional SVG icon */
[dir="rtl"] .icon--directional { transform: scaleX(-1); }
```

| Icon type                | Mirror? |
|--------------------------|---------|
| Back / forward arrow     | YES     |
| Breadcrumb chevron       | YES     |
| Progress indicator       | YES     |
| Play / pause button      | NO      |
| Warning / error triangle | NO      |
| Checkbox tick            | NO      |
| Logo / brand mark        | NO      |

## Anti-patterns

- Using `margin-left` / `padding-right` in new components
  instead of logical properties — breaks as soon as
  `dir="rtl"` is set anywhere in the ancestor chain.
- Flipping the whole page with `transform: scaleX(-1)` on
  `<body>` — text renders as unreadable mirror-text.
- Setting `direction: rtl` on isolated components without
  `dir="rtl"` on `<html>` — the Unicode Bidi Algorithm
  does not engage, producing garbled mixed-direction text.
- Mirroring non-directional icons (logos, alert icons).
- Using `text-align: left` instead of `text-align: start`.

## Gotchas

- Flexbox reverses its main axis automatically in RTL when
  `direction` is inherited. Adding explicit `flex-direction:
  row-reverse` on top of RTL double-reverses back to LTR
  — a common accidental no-op.
- `position: absolute` with `left: 0` does not flip in RTL.
  Use `inset-inline-start: 0` for auto-flipping.
- CSS Grid column order is not automatically mirrored. Set
  `direction: rtl` on the grid container explicitly.
- Bidirectional text inside RTL containers needs `<bdi>`
  or `unicode-bidi: isolate` to prevent digit reordering.

## Verification

- Toggle `dir="rtl"` on `<html>` in DevTools; the layout
  should mirror without overflow or clipping artifacts.
- Run visual-regression snapshots in both `dir="ltr"` and
  `dir="rtl"` (Playwright screenshot, Percy, or Chromatic).
- `grep -rn "margin-left\|padding-right\|padding-left\
  \|margin-right" src/` should return zero results in
  components written after the logical-property migration.
- Add a `withRTL` Storybook decorator wrapping each story
  in `<div dir="rtl">` to catch per-component regressions.

## Related

- `i18n/bidi-rtl-layout-css.md`
- `i18n/css-logical-properties-2026.md`
- `i18n/i18n-rtl-testing-2026.md`
- `i18n/rtl-safe-component-patterns.md`
- `i18n/hebrew-rtl-react.md`

## Source URLs (verified 2026-08-17)

- https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_logical_properties_and_values
- https://developer.mozilla.org/en-US/docs/Web/HTML/Global_attributes/dir
- https://tailwindcss.com/docs/hover-focus-and-other-states#rtl-support
- https://rtlstyling.com/posts/rtl-styling
- https://material.io/design/usability/bidirectionality.html
