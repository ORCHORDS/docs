# Hidden-until-found and beforematch reveal

**Issue:** Collapsed content is absent from find-in-page and fragment navigation, so users can search for matching text but cannot reach or see it.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** progressive enhancement; browser support varies

HTML's `hidden="until-found"` allows hidden content to participate in find-in-page and fragment matching. Before revealing it, the browser dispatches `beforematch`, letting an application synchronize disclosure state.

**Source:** [WHATWG HTML — the hidden attribute](https://html.spec.whatwg.org/multipage/interaction.html#the-hidden-attribute)

## Controls

- use only for content that is legitimately searchable while collapsed;
- handle `beforematch` idempotently and update the owning disclosure state;
- keep headings, landmarks, and fragment IDs stable;
- avoid expensive synchronous work in the reveal handler;
- supply an ordinary disclosure control and unsupported-browser fallback.

## Verification

Test browser find, text fragments, URL fragments, nested collapsed regions, repeated matches, history navigation, keyboard focus, printing, and unsupported engines. Confirm revealed content is visible and scrolled without duplicate state transitions.

## Gotchas

This is not a security or lazy-loading boundary: hidden content remains in the document. CSS containment requirements affect rendering. Do not put secrets or unauthorized data in the DOM.
