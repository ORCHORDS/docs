# i18n-rtl-testing-2026

**Issue:** A team ships to Arabic and Hebrew markets. The team sees layout overflows, icons pointing the wrong way, mixed-direction text rendering broken. The team needs a 2026 RTL testing reference.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 RTL failure modes

1. **Absolute positioning.** `left: 10px` not mirrored in RTL.
2. **Hardcoded text direction.** `text-align: right` for English text in RTL context.
3. **Icon direction.** Arrow icons point wrong way; back/forward swap.
4. **Logical properties missing.** `margin-left` instead of `margin-inline-start`.
5. **Mixed-direction content.** English inside Arabic message without `<bdi>`.

## The 5 test types

1. **Visual regression per locale.** Screenshot Arabic + Hebrew in key states.
2. **Mixed content tests.** Arabic message with English username, URL, phone number.
3. **Bidirectional algorithm tests.** Verify Unicode Bidi algorithm output.
4. **Icon mirroring tests.** All directional icons flipped in RTL.
5. **Logical property audit.** `grep` for `margin-left|right|padding-left|right` in CSS.

## The 5-step RTL readiness audit

1. **Toggle `dir="rtl"` on `<html>`** in test environment.
2. **Screenshot all key states** with Playwright/Cypress.
3. **Check for overflow** (text bleeding out of containers).
4. **Check icon direction** (arrows, back, forward).
5. **Test mixed content** (RTL + Latin in same string).

## The 5 best practices

1. **Use logical CSS properties** (`margin-inline-start`, `padding-inline-end`).
2. **Set `dir` on `<html>`**, not on individual components.
3. **Wrap mixed-direction content** in `<bdi>`.
4. **Mirror directional icons** with `transform: scaleX(-1)` in RTL.
5. **Test real RTL locales** (ar, he, fa, ur) early.

## Gotchas

- `transform: scaleX(-1)` flips text glyphs too; use `transform: scaleX(-1)` only on icons.
- Browser DevTools can toggle `dir`; useful for spot-checks.
- Some icon libraries (Material Icons) have `rtl` variants; use them.
- Logical properties are supported in 95%+ of browsers; safe to use.
- `[dir="rtl"]` parent selector for any RTL-specific overrides.

## Source URLs (verified 2026-08-10)

- https://www.w3.org/International/articles/inline-bidi-markup/
- https://rtlstyling.com/
- https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_Logical_Properties
- https://github.com/google/material-design-icons
