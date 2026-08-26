# CSS Logical Properties for i18n (2026)

## Symptom

You ship an Arabic (`ar`) or Hebrew (`he`) locale and the layout breaks:
icons overlap text, chevrons point the wrong way, `margin-left` pushes
content off-screen, and every RTL bug forces a new `[dir="rtl"]` override
block. Your CSS file balloons with duplicate rules and half of them fight
each other.

The root cause is **physical properties** (`left`, `right`, `top`, `bottom`,
`margin-left`, `text-align: left`). They hard-code a direction. When the
`dir` attribute flips, the physical values do not, so you patch them by hand.

## The fix: logical properties

CSS Logical Properties (stable, Baseline 2023, universal in 2026 browsers)
use **flow-relative** axes that respect the writing direction automatically:

| Physical (avoid)        | Logical (prefer)            |
|-------------------------|-----------------------------|
| `margin-left`           | `margin-inline-start`       |
| `margin-right`          | `margin-inline-end`         |
| `padding-left`          | `padding-inline-start`      |
| `border-top`            | `border-block-start`        |
| `left: 0`               | `inset-inline-start: 0`     |
| `right: 0`              | `inset-inline-end: 0`       |
| `width`                 | `inline-size`               |
| `height`                | `block-size`                |
| `text-align: left`      | `text-align: start`         |
| `text-align: right`     | `text-align: end`           |
| `float: left`           | `float: inline-start`       |

Set `<html dir="rtl">` once and **every** logical property flips for free.

## Gotchas

- **`text-align: start` needs the `dir` attribute set.** If you forget
  `<html dir="rtl">` (or `dir="ltr"`), `start` defaults to the browser's
  guess. Always set `dir` explicitly on the root element.
- **Absolute positioning still uses physical `top`/`bottom`.** `top` and
  `bottom` map to `block-start`/`block-end` only for horizontal writing
  modes. For vertical-RL (e.g. traditional Japanese `writing-mode:
  vertical-rl`) they behave differently. Use `inset-block-start`.
- **Shorthands flip order in RTL.** `margin-inline: 10px 20px` means
  start=10, end=20. In LTR that's left=10/right=20; in RTL it becomes
  right=10/left=20. This is usually what you want, but verify.
- **Third-party CSS may use physical properties.** If you drop in a
  component library that hard-codes `margin-left`, logical properties on
  your side won't save it. Audit dependencies or wrap with `dir`-scoped
  overrides.
- **`resize: horizontal` and some animations keyframe physical values.**
  `transform: translateX(100px)` does NOT flip. Use `translate` with
  logical units or flip the sign with a `[dir="rtl"]` rule for transforms.
- **Icons and directional imagery need logical `scale` or separate assets.**
  A right-arrow chevron in LTR should become a left-arrow in RTL. Use
  `scale: -1 1` under `[dir="rtl"]` or swap the SVG source.
- **`float: inline-start` has older-browser gaps.** Safari < 15 and any
  non-Chromium Edge may need a `float: left` fallback. Check your browser
  matrix.
- **Logical properties do not auto-fix `box-shadow` offsets or `clip-path`.**
  A `box-shadow: 4px 0 0 red` stays on the left edge. Annotate and override.

## Quick checklist

1. Set `<html lang="ar" dir="rtl">` (or `ltr`) on every document.
2. Grep your CSS for `left|right` and replace with `inline-start|inline-end`.
3. Replace `text-align: left/right` with `start/end`.
4. Test with `dir="rtl"` on a real Arabic/Hebrew string, not example text.
5. Run a pseudo-localization pass to catch overflow caused by longer strings.
