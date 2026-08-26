# Native exclusive accordions with the details name attribute

**Issue:** Scripted accordions frequently drift from native disclosure semantics and can leave multiple panels open or focus state inconsistent.
**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Build each disclosure as `<details name="group"><summary>…</summary>…</details>`; equal `name` values form an exclusive group.
- Provide a visible, descriptive `summary` and keep headings/landmarks inside the panel where they preserve the document outline.
- Ensure only one member of a named group starts with `open`; source order determines the winner if markup is inconsistent.
- Use the `toggle` event only for ancillary state or analytics, not to recreate the browser's exclusivity algorithm.
- Preserve a usable non-exclusive fallback where support is incomplete; content must remain reachable without JavaScript.

## Verification

1. Activate every summary by keyboard, pointer, and assistive technology and verify exactly one grouped disclosure remains open.
2. Deep-link/focus a control inside a closed panel and define whether application code should open it.
3. Test back/forward restoration, print styles, DOM insertion/removal, nested groups, and duplicated names in separate components.
4. Check screen-reader announcement of expanded/collapsed state in supported browser/AT combinations.
5. Verify analytics tolerates coalesced `toggle` events rather than counting every intermediate state.

## Gotchas

The `name` attribute creates exclusivity even when elements are not adjacent, so globally reused names can couple unrelated components. The group must not be used when users need to compare several panels simultaneously. Styling the marker does not replace the summary's semantics. Browser support should be measured against the project's matrix.

## Sources

- [MDN: details element and named disclosure groups](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/details)
- [WHATWG HTML: the details element](https://html.spec.whatwg.org/multipage/interactive-elements.html#the-details-element)
