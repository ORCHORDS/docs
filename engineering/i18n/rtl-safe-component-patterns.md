# rtl-safe-component-patterns

**Issue:** RTL layout breaks with `margin-left` + English brand text
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your app supports Arabic (`ar`) and Hebrew (`he`). You write a
button with `margin-left: 12px` to space the icon from the text.
In Arabic, the icon now appears on the WRONG side (left when it
should be right).

## Root cause
Physical CSS properties (`margin-left`, `padding-right`,
`border-left`) ignore the document's text direction. The user is
reading right-to-left, so the "left" side of the screen is the
"end" of the reading flow, not the "start."

Logical CSS properties (`margin-inline-start`, `padding-inline-end`,
`border-inline-start`) adapt to the text direction automatically.

**Source:** MDN — Logical properties:
https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_logical_properties_and_values

> "Logical properties use the terms 'inline' and 'block' to
> describe the direction in which the flow of content occurs.
> They make it easier to author CSS that works for different
> writing modes and directions."

## Fix
Replace physical properties with logical equivalents:

```css
/* ❌ Physical — breaks in RTL */
.button { margin-left: 12px; padding-right: 8px; border-left: 2px solid; }

/* ✅ Logical — works in LTR and RTL */
.button {
  margin-inline-start: 12px;
  padding-inline-end: 8px;
  border-inline-start: 2px solid;
}
```

| Physical | Logical |
|---|---|
| `margin-left` | `margin-inline-start` |
| `margin-right` | `margin-inline-end` |
| `padding-left` | `padding-inline-start` |
| `padding-right` | `padding-inline-end` |
| `border-left` | `border-inline-start` |
| `border-right` | `border-inline-end` |
| `left` (positioning) | `inset-inline-start` |
| `right` (positioning) | `inset-inline-end` |
| `text-align: left` | `text-align: start` |
| `text-align: right` | `text-align: end` |
| `float: left` | `float: inline-start` |
| `float: right` | `float: inline-end` |

## `<bdi>` for mixed-direction text

When the text content is mixed (e.g. Arabic + English brand name),
wrap the LTR text in `<bdi>`:

```html
<p>
  مرحبا بك في <bdi>THE PLATFORM</bdi>
  <!-- "Welcome to THE PLATFORM" — the brand stays LTR in RTL flow -->
</p>
```

Without `<bdi>`, the English brand name may flip or align oddly.

## `<bdo>` for explicit override

When you need to FORCE a direction (rare, e.g. for an Arabic
tutorial that wants to show the English string "as the user would
type it"):

```html
<p>اكتب <bdo dir="ltr">Hello World</bdo> في الحقل</p>
```

`<bdo>` is bidirectional override — it changes the base direction
for its content. Use sparingly; it can disorient screen readers.

## CSS `dir` attribute

```html
<html dir="rtl" lang="ar">
```

Setting `dir="rtl"` on `<html>` (or any container) flips the
logical-property defaults. The same `margin-inline-start: 12px`
becomes 12px on the right side.

## Verification
- **Test:** `test/rtl.test.ts > component renders correctly in RTL`
  — visual snapshot for ar and he locales
- **Live:** `ar-SA` and `he-IL` browser sessions — buttons, nav,
  forms all mirrored correctly
- **Visual QA:** 20-locale screenshot pass — confirm brand text
  wrapped in `<bdi>` stays LTR even in RTL pages

## Gotchas
- **Icons that imply direction** (arrows, "next" buttons) should
  also flip in RTL. Use `transform: scaleX(-1)` on the SVG, or
  swap the icon entirely (e.g. "→" becomes "←").
- **Numbers are LTR even in RTL context.** `123` stays
  left-to-right. Wrap in `<bdi>` if the surrounding text is
  long enough that the number might wrap awkwardly.
- **NOT all CSS properties have logical equivalents.** `width`,
  `height`, `top`, `bottom` are physical. Use logical for spacing
  + positioning, but width/height are fine.
- **Logical properties are supported in all modern browsers** as
  of 2021. For legacy support, you may need a CSS-in-JS polyfill
  or fall back to physical properties + RTL overrides.
- **Some frameworks (Bootstrap 5+, Tailwind 3+) have built-in
  RTL support.** Use the framework's logical-property utilities
  instead of writing your own.

## Related
- `brand-literals-stay-english.md`
- MDN: https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_logical_properties_and_values
- MDN `<bdi>`: https://developer.mozilla.org/en-US/docs/Web/HTML/Element/bdi
- MDN `<bdo>`: https://developer.mozilla.org/en-US/docs/Web/HTML/Element/bdo
