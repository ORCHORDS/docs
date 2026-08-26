# inert-attribute-accessibility

**Issue:** Hidden content keeps stealing keyboard focus: tabbing through a page lands inside a collapsed sidebar, a closed `<details>`, an off-screen carousel slide, or behind an open modal. The traditional fixes are broken in different ways — `display: none` unmounts animations and state, `visibility: hidden` needs per-descendant overrides to re-expose content, and `aria-hidden="true"` hides from screen readers but leaves elements focusable for sighted keyboard users, which is itself an accessibility violation (focusable aria-hidden content). The HTML `inert` global attribute solves all of this natively: one attribute removes a subtree from the tab order, the accessibility tree, AND blocks pointer/text events, without unmounting it.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Semantics: what inert actually does

1. **Removes the subtree from sequential focus navigation.** No element inside an inert subtree can be focused by Tab, Shift+Tab, `focus()` calls, or clicking. Elements that were focused when `inert` is applied lose focus immediately.
2. **Blocks all activation and input events.** Clicks, pointer events, text input, and editing commands on inert content fire nothing — the browser treats the subtree as non-interactive for the user, while your own JavaScript can still read and mutate it programmatically.
3. **Hides the subtree from the accessibility tree.** Screen readers do not announce inert content, equivalent to `aria-hidden` but without the focusable-descendants violation, because inert descendants cannot receive focus in the first place. This is exactly why current guidance (e.g., University of Washington accessibility, Nov 2025) prefers `inert` over `aria-hidden` for non-interactive regions.
4. **It is purely presentational — the DOM is untouched.** Inputs keep their values, scroll positions persist, media keeps playing (unless you pause it), CSS animations continue. This is the key difference from `display: none` and why `inert` is ideal for temporarily suppressing content you intend to bring back.
5. **Baseline widely available since ~2023.** All major browsers (Chromium, Firefox, Safari) support it unprefixed in 2026; no polyfill needed for current targets. Older codebases may still carry the historical `inert` polyfill from before Firefox 112 / Safari 15.5 — it can be deleted.

## inert vs the alternatives

1. **vs `aria-hidden="true"`.** Use `aria-hidden` only when content is already non-interactive and you just want it unannounced (decorative icons, duplicated text). If anything inside is focusable, `aria-hidden` creates the "hidden but tabbable" violation; `inert` cannot create that state.
2. **vs `display: none`.** `display: none` removes from layout entirely (content collapses, state like iframe/video resets in some engines, transitions cannot animate out). `inert` keeps content painted, so you can animate the transition to invisibility and then flip to `display: none` at animation end if needed.
3. **vs `visibility: hidden`.** Similar suppression, but `visibility` inherits and must be manually re-enabled per visible descendant, which does nothing about clickability semantics and gets messy with positioned popovers. `inert` is one attribute on one wrapper.
4. **vs `pointer-events: none` (CSS).** This only blocks the mouse — keyboard activation and focus are untouched. Any CSS overlay built on `pointer-events` for "disabling" a region is incomplete; pair it with `inert` or replace it.
5. **vs `disabled` on form controls.** `disabled` works per-control, does not cover links or non-form content, dims semantics differently, and removes values from form submission. `inert` on the form container is a blunt instrument that also keeps inputs submittable when un-inerted — choose per use case.

## Real-world applications

1. **Modal dialogs (the canonical case).** When a `<dialog>` opens via `showModal()`, the browser handles background inertiity for you. But for non-native modals (custom overlays, side sheets built with `popover`), apply `inert` to the page wrapper (header, nav, main, footer — everything except the overlay and its portal target) for the duration. This achieves focus containment without a hand-rolled focus-trap library.
2. **Off-screen carousel and slider content.** Slides translated out of view are still in the tab order and screen-reader order. Mark non-visible slides `inert` and flip it as the active slide changes, so Tab moves through the visible slide's content only.
3. **Route/page transitions.** During a cross-fade view transition, mark the outgoing view `inert` so users cannot interact with (or focus) a page that is animating away and about to unmount.
4. **Collapsed regions (accordions, nav drawers, tabs).** Content that is visually hidden but still mounted (height 0, opacity 0) should be `inert` while collapsed; remove it on expand. Without this, keyboard users tab through invisible fields.
5. **Content behind a skeleton/loading state.** While a panel is loading and showing a skeleton, the stale content behind it can be `inert` so clicks and focus do not hit stale interactive elements mid-swap.

## Gotchas

1. **Focus does not come back on un-inert automatically.** When the overlay closes, move focus deliberately (to the element that opened it, or the document heading) — un-inerting restores tabbability but nothing restores focus by itself. This pairs with the focus-management rules in `web-accessibility-focus-management.md`.
2. **Applying inert to an ancestor of the currently focused element blur fires with no target context.** Always store `document.activeElement` before opening an overlay so you know where to restore focus.
3. **Do not put the inert attribute on `<body>` or `<html>`.** It is a global attribute but inerting the root kills the whole document including your overlay if it lives anywhere in the tree. Target specific page-regions and keep overlay portals outside them.
4. **The attribute value does not matter but presence does.** `inert="false"` is STILL inert — it is a boolean attribute; remove the attribute entirely to re-activate. React 19 supports `inert={true}` properly; in older React you needed `inert=""` (or `inert` as a string) because React did not recognize it as a boolean attribute.
5. **Screen readers' browse mode vs focus mode.** Inert hides content from the accessibility tree in both modes in modern engines, but always test with a real screen reader (NVDA + Chrome, VoiceOver + Safari) — historical polyfill-era behavior lingers in older AT versions on locked-down enterprise browsers.
6. **Do not confuse suppression with security.** Inert blocks UI interaction, not programmatic access: scripts, devtools, and network-level access to that content are unaffected. Never use it to "disable" content that must be access-controlled server-side.

## Testing

1. **Keyboard-only walkthrough as a first-class test.** With an overlay open, Tab through the entire document and assert focus never lands inside the background content; automate with Playwright by collecting `document.activeElement` across Tab presses.
2. **axe-core catches the inverse bug.** Run axe on pages using `aria-hidden` for suppression — the "aria-hidden-focus" rule flags focusable hidden content and points exactly where `inert` should replace it.
3. **Assert attribute removal, not value.** Playwright assertions like `expect(wrapper).not.toHaveAttribute('inert')` — checking `getAttribute('inert') !== 'false'` misses the boolean-attribute trap above.
4. **Related reading in this knowledge base:** `native-popover-dialog-anchor.md` (where `showModal` already inerts the background), `web-accessibility-focus-management.md` (focus restoration rules), `wcag-2-2-accessibility-compliance.md` (2.4.3 Focus Order).
