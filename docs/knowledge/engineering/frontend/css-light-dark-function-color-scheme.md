# CSS Light Dark Function Color Scheme

## Scope

Using the `light-dark()` CSS color function to define one color pair that switches with the used color scheme, replacing per-theme overrides and duplicated custom properties. Covers how `color-scheme` enables the switch, where `light-dark()` may appear (including custom property declarations), how it interacts with `prefers-color-scheme` and user-forced themes, and what still needs explicit theming. Excludes design-token pipelines that generate themes at build time and excludes the older `filter: invert()` dark-mode hacks.

## Workflow or implementation guidance

The problem: a component library supports light and dark themes. The classic pattern is a `:root { --surface: #fff; } :root[data-theme="dark"] { --surface: #111; }` pair for every color, which doubles the token block and drifts out of sync. `light-dark()` collapses each pair into one expression whose result is chosen by the color scheme in effect for that element.

The function is inert without a color scheme declared, so the enabling step comes first.

```css
:root {
  color-scheme: light dark;
}
```

With `color-scheme: light dark`, the browser applies the user-preferred scheme by default, and forced-color or OS-level preferences propagate into the used scheme. Then colors become single declarations.

```css
:root {
  --surface: light-dark(#ffffff, #121212);
  --ink: light-dark(#1a1a1a, #f2f2f2);
  --accent: light-dark(#0b57d0, #a8c7fa);
}

.button {
  background: var(--surface);
  color: var(--ink);
  border: 1px solid light-dark(#0002, #fff2);
}
```

When the page lets the user pin a theme instead of following the OS, set the used color scheme per subtree. `color-scheme` is inherited, so applying it on the root element with a data attribute is the standard control point.

```css
:root[data-theme="dark"] { color-scheme: dark; }
:root[data-theme="light"] { color-scheme: light; }
```

Because `light-dark()` resolves against the element's used color scheme (not against a media query), theme switching is a single property change — no re-resolving of two token blocks, and works inside shadow roots where a media-query-driven cascade duplication would otherwise be needed per component.

Place it in custom property declarations, as above, so component CSS never mentions themes at all. This is the key architectural benefit: components consume semantic tokens; only the token definition site knows that light and dark exist. Shadows and translucency benefit too — one `light-dark()` call replaces the "light needs softer shadow, dark needs lighter hairline" pair.

Fallback for browsers without support uses the pre-existing cascade: keep a plain value before the `light-dark()` line, since unsupported declarations are dropped by the CSS parser.

```css
--surface: #ffffff;
--surface: light-dark(#ffffff, #121212);
```

During migration, grep for `@media (prefers-color-scheme: dark)` blocks that only redefine custom properties and convert them one token at a time; leave media-query blocks in place where the switch depends on something other than the color scheme (for example, a layout change at a width breakpoint).

## Controls

- `color-scheme` on `:root` (values `light`, `dark`, or both) enables the function and also fixes form-control and scrollbar default rendering per scheme.
- `light-dark(<light>, <dark>)` accepts any color value in each slot, including color-mix and relative color syntax where supported.
- User-pinned themes override OS preference by setting `color-scheme` on the root element via attribute or class; the attribute write is the single theme-switch control point.
- Respect forced colors: `@media (forced-colors: active)` remains the correct place to strip backgrounds and rely on system colors; `light-dark()` is not involved there.

## Validation evidence

- Toggle the OS appearance or the data attribute and confirm computed values flip: `getComputedStyle(el).color` in dark scheme must equal the second argument's computed color.
- Screenshot-diff both schemes per component in CI; a token defined with mismatched slots (dark value in the light slot) shows up as an unreadable pair rather than a console error.
- Verify form controls and scrollbars switch with the scheme — this validates that `color-scheme` was actually set, not just colors hardcoded twice.
- Confirm accessibility contrast in both slots with an automated checker; each pair must independently pass its target ratio, since the function guarantees switching, never contrast.

## Failure modes and correction

- `light-dark()` always returns the light value even in OS dark mode: `color-scheme` was not declared (or was declared on a different subtree). Declare it on `:root`, or on the theming wrapper when themes are per-subtree.
- Theme toggle inside a shadow root component has no effect: `color-scheme` inherits, so setting it on `:root` covers shadow trees, but setting it only inside the shadow root leaves the outer page light. Decide at the page boundary.
- Duplicate declarations kept as fallback drift out of sync after a palette change. Add a build lint that fails when a token declares the fallback form and the token definition has since changed slots.
- Mixing `light-dark()` with `@media (prefers-color-scheme: dark)` overrides for the same token creates a precedence puzzle; the media query wins on specificity/order regardless of scheme. Convert the override to the function or remove it.
- Nested components with their own hardcoded `color-scheme: light` for "always light" widgets (for example a code block) — that is legitimate, but document it, because it silently opts descendants out of theme switching.
- Color-space confusion: values are used as authored; converting between sRGB and display-p3 happens per slot by the normal color rules. Mixing wide-gamut and sRGB slots produces inconsistent saturation across schemes; author both slots in the same color space.

## Limitations

- Only two schemes are addressable (the light and dark slots); additional themes (brand overrides, high contrast) still need custom property sets alongside it.
- Browser support excludes older evergreen versions; the cascade-fallback pattern must remain during the support window.
- The switch follows the used color scheme, so any logic that depends on knowing which slot is active in CSS (for example adjusting a shadow direction) still needs `prefers-color-scheme` or a data attribute.
- JavaScript cannot read which slot `light-dark()` resolved to; code that needs the active scheme must read `matchMedia('(prefers-color-scheme: dark)')` or the theme attribute, which can disagree with an element-level `color-scheme` override.
- Images, video, and non-color styling (font weight, spacing) are unaffected; `light-dark()` solves only the color-pair duplication.

## Canonical sources

- CSS Working Group, CSS Color Adjustment Module Level 1, `light-dark()`: https://drafts.csswg.org/css-color-adjust-1/#light-dark
- MDN, `light-dark()` color function: https://developer.mozilla.org/en-US/docs/Web/CSS/color_value/light-dark
- MDN, `color-scheme` property: https://developer.mozilla.org/en-US/docs/Web/CSS/color-scheme
- MDN, `prefers-color-scheme` media feature: https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-color-scheme
