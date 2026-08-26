# accessibility-wcag

**Issue:** WCAG 2.2 AA — practical implementation for a consumer app
**Date:** 2026-08-09
**Status:** documented

## Symptom
You ship a feature. A user with a screen reader reports "the
button is unlabeled." You add `aria-label`. Another user
reports "the form has no error messages." You add error
handling. The cycle continues. You never get to a passing
WCAG audit.

## Root cause
**Accessibility is a system-level concern, not a per-feature
patch.** Each new feature must be built with accessibility in
mind. Otherwise, you accumulate bugs that compound.

**Source:** WCAG 2.2:
https://www.w3.org/TR/WCAG22/

## The 4 POUR principles

### 1. Perceivable
- **Alt text for images:** `alt="Description"` (or `alt=""` for
  decorative)
- **Captions for video:** `<track kind="captions">`
- **Color contrast:** 4.5:1 for text, 3:1 for large text
- **Don't rely on color alone:** include text or shape

### 2. Operable
- **Keyboard navigation:** all interactive elements reachable
  via Tab
- **Focus indicator:** visible focus ring (not removed via
  CSS)
- **Skip links:** "Skip to main content" for screen readers
- **No keyboard traps:** modals can be closed via Escape
- **Touch target size:** 44x44px minimum

### 3. Understandable
- **Language attribute:** `<html lang="en">`
- **Form labels:** `<label for="email">Email</label>`
- **Error messages:** specific, actionable, associated with the
  field
- **Consistent navigation:** the menu is the same on every page

### 4. Robust
- **Valid HTML:** no missing closing tags, no invalid attributes
- **ARIA used correctly:** prefer semantic HTML over ARIA when
  possible
- **Compatible with assistive tech:** test with NVDA, JAWS,
  VoiceOver, TalkBack

## Common fixes

### Missing alt text
```html
<!-- ❌ Bad -->
<img >

<!-- ✅ Good -->
<img  alt="Acme Corp">
<!-- or for decorative images -->
<img  alt="" role="presentation">
```

### Unlabeled form input
```html
<!-- ❌ Bad -->
<input type="email" name="email" placeholder="Email">

<!-- ✅ Good -->
<label for="email">Email</label>
<input type="email" id="email" name="email" placeholder="you@example.com" required>
```

### Button without accessible name
```html
<!-- ❌ Bad -->
<button><svg>...</svg></button>

<!-- ✅ Good -->
<button aria-label="Close"><svg aria-hidden="true">...</svg></button>
```

### Modal without focus trap
```html
<!-- ❌ Bad: tabbing leaves the modal -->
<div class="modal">...</div>

<!-- ✅ Good: focus is trapped, Escape closes -->
<div role="dialog" aria-modal="true" aria-labelledby="modal-title">
  <h2 id="modal-title">Confirm deletion</h2>
  ...
</div>
```

## Testing tools

### Automated
- **axe-core** — DevTools extension, catches ~30% of issues
- **Pa11y** — CI-friendly, command-line
- **Lighthouse** — Chrome DevTools, basic audit

### Manual
- **NVDA** (Windows) — free screen reader
- **VoiceOver** (macOS / iOS) — built-in
- **TalkBack** (Android) — built-in
- **Keyboard-only navigation** — unplug the mouse

### User testing
- **Recruit users with disabilities** for real-world testing
- **Assistive tech users** are the source of truth

## Verification
- **Test:** `test/a11y.test.ts > axe scan on key pages returns
  0 violations` — passes
- **Live:** Lighthouse accessibility score > 95
- **Audit:** Annual third-party WCAG 2.2 AA audit

## Gotchas
- **Automated tools catch ~30% of issues.** Manual testing
  (especially with assistive tech) catches the rest.
- **ARIA is not a substitute for semantic HTML.** `<div role="button">`
  is worse than `<button>`. Use HTML first, ARIA as a fallback.
- **"Accessible" is not a binary state.** It's a spectrum.
  WCAG 2.2 AA is the legal bar; AAA is the gold standard.
- **For 21+ social platforms**, accessibility is especially
  important for users with disabilities who may rely on
  assistive tech. Don't cut corners.
- **Live regions for dynamic content:** if a notification
  appears, use `aria-live="polite"` so screen readers
  announce it.
- **Color contrast tools:** WebAIM Contrast Checker
  (https://webaim.org/resources/contrastchecker/)

## Related
- `i18n/rtl-safe-component-patterns.md` (RTL is part of a11y)
- WCAG 2.2: https://www.w3.org/TR/WCAG22/
- WebAIM: https://webaim.org/
- axe-core: https://github.com/dequelabs/axe-core
- Pa11y: https://pa11y.org/
