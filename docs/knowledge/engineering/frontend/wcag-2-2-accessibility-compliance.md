# WCAG 2.2 Accessibility Compliance (2026)

## Symptom

You get a bug report: "Screen reader users cannot complete checkout" or
"Keyboard-only users are stuck." Or legal asks for a VPAT / accessibility
conformance report because a customer (or the EU European Accessibility Act,
in force since June 2025) requires WCAG 2.2 compliance. Your existing a11y
checks were built around WCAG 2.1 and you are not sure what changed.

WCAG 2.2 added nine new success criteria (mostly Level A/AA) on top of 2.1.
It is a strict superset — anything compliant with 2.2 is compliant with 2.1.

## The nine new success criteria (2.2 additions)

### Level A
1. **2.4.11 Focus Not Obscured (Minimum)** — focused element must be at least
   partially visible. Sticky headers/footers that cover the focused field
   fail this.
2. **2.4.13 Focus Appearance** — focus indicator must be clearly visible
   (size and contrast minimums).

### Level AA
3. **2.4.11 Focus Not Obscured (Minimum)** — (same as above, AA also).
4. **2.5.7 Dragging Movements** — any drag interaction must have a
   non-drag alternative (click/tap). Sliders, Kanban drag-drop, range inputs.
5. **2.5.8 Target Size (Minimum)** — clickable targets at least 24x24 CSS
   pixels, OR enough spacing that adjacent targets do not overlap their
   24px circles.
6. **3.2.6 Consistent Help** — if help mechanisms (contact, FAQ, chat) are
   on multiple pages, they appear in the same relative order on each.
7. **3.3.7 Redundant Entry** — multi-step forms must auto-fill or allow
   re-use of data entered in earlier steps.
8. **3.3.8 Accessible Authentication (Minimum)** — no cognitive function
   test (e.g., transcribe distorted text) as the only auth method.

### Level AAA
9. **2.4.12 Focus Not Obscured (Enhanced)** — focused element fully visible
   (no partial).

## Gotchas

### `outline: none` without a replacement is now a clear failure

Removing the default focus ring without providing a visible custom indicator
fails 2.4.13. Always define a focus-visible style:

```css
:focus-visible {
  outline: 2px solid var(--focus-ring, #2563eb);
  outline-offset: 2px;
}

/* DO NOT do this without a replacement */
:focus { outline: none; }
```

### Sticky headers block focused form fields

```css
/* FAILS 2.4.11 — sticky header overlaps the focused input */
.header { position: sticky; top: 0; height: 80px; z-index: 10; }
input:focus { /* hidden behind header on small screens */ }
```

Fix: add `scroll-margin-top` to focusable elements, or use
`scroll-padding-top` on the scroll container.

```css
input, button, a, [tabindex] {
  scroll-margin-top: 96px;  /* clear the sticky header */
}

html { scroll-padding-top: 96px; }
```

### Drag-and-drop without a click alternative fails 2.5.7

A Kanban board where cards can ONLY be moved by dragging fails. Add a
"Move" menu or keyboard shortcut (arrow keys, context menu).

### 24x24 CSS pixel target — spacing can substitute

```css
/* Each icon button is 20x20 but spaced 14px apart -> circles overlap
   within 24px -> FAILS 2.5.8 */
.toolbar button { width: 20px; height: 20px; margin: 2px; }
```

Fix: make buttons 24x24, OR increase spacing so the 24px circles around
adjacent targets do not overlap.

### Redundant entry bites checkout and onboarding

A 3-step checkout asking for the billing address, then the shipping address,
with no "same as billing" checkbox fails 3.3.7. Provide auto-fill or a
copy toggle.

### CAPTCHA as the only auth path fails 3.3.8

Distorted-text CAPTCHA alone fails. Provide an alternative: WebAuthn /
passkey, email magic link, or identity-provider login. This is also why
passkey-first auth became the default in 2026 designs.

### Automated tools catch ~30% — manual testing is required

axe-core, Lighthouse, and WAVE catch structural issues (missing alt,
contrast, ARIA misuse) but cannot judge:
- Focus order across complex widgets (test with Tab/Shift+Tab).
- Screen-reader announcement quality (test with NVDA + Firefox, VoiceOver +
  Safari).
- Whether dragging has a keyboard alternative.

Run both: axe in CI for regressions, plus quarterly manual audits with real
AT (assistive technology) users.

## Practical checklist for a new feature

- [ ] Every interactive element has a visible `:focus-visible` style.
- [ ] Focusable elements have `scroll-margin-top` if a sticky header exists.
- [ ] Drag interactions have a click/keyboard alternative.
- [ ] Click targets are >= 24x24 CSS px (or spaced to not overlap).
- [ ] Multi-step forms re-use or auto-fill earlier data.
- [ ] Auth path has a non-CAPTCHA option (passkey, link, SSO).
- [ ] axe-core passes with zero serious/critical violations.
- [ ] Keyboard-only walkthrough completes the core task.
- [ ] Screen-reader walkthrough announces all state changes.
