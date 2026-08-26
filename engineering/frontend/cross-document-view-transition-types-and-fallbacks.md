# Cross-Document View Transition Types and Fallbacks

**Issue:** Multi-page view transitions can improve navigation continuity, but unsupported browsers, cross-origin redirects, duplicate transition names, and motion preferences can produce broken or inaccessible navigation.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Opt both source and destination documents into eligible same-origin navigation with `@view-transition { navigation: auto; }`. Use the `types` descriptor only for a small semantic vocabulary such as forward, backward, detail, or overview; select animations with `:active-view-transition-type()` rather than binding behavior to individual URLs.

Keep links and server navigation fully functional without the transition. Assign `view-transition-name` only to stable visual counterparts and ensure names are unique in the rendered document. Treat transition CSS as enhancement: content, focus order, history, and accessible names must not depend on captured transition pseudo-elements.

Respect `prefers-reduced-motion: reduce` by disabling or materially simplifying motion. Avoid long animations that delay comprehension or create the impression navigation is blocked.

## Verification

Test push, replace, and browser-history traversal; same-origin redirects; cross-origin navigation; back/forward cache restoration; duplicate names; slow images; and unsupported engines. During animation, verify the destination URL, focus placement, scroll restoration, keyboard navigation, and assistive-technology reading order. Capture reduced-motion screenshots and run the normal accessibility suite.

## Gotchas

Cross-document transitions require same-origin documents and eligible user-initiated navigation; browser UI navigation and redirects can change eligibility. The feature is not universally available, so never gate routing on it. Snapshot pseudo-elements are visual copies, not interactive replacements.

## Sources

- [MDN @view-transition](https://developer.mozilla.org/en-US/docs/Web/CSS/@view-transition)
- [MDN using view-transition types](https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API/Using_types)
- [CSS View Transitions Module Level 2](https://drafts.csswg.org/css-view-transitions-2/)
