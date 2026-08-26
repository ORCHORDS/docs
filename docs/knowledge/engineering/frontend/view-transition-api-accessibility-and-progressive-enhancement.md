# View Transition API accessibility and progressive enhancement

**Issue:** A site adds animated SPA/MPA transitions that cause focus confusion, motion discomfort, or broken navigation in unsupported browsers.
**Date:** 2026-08-12
**Author:** ORCHORDS
**Status:** documented

The View Transition API can animate DOM-state changes and same-origin document navigation. It is an enhancement: the state update/navigation must work correctly without it.

**Sources:**

- [MDN View Transition API](https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API)
- [Using the View Transition API](https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API/Using)

## Pattern

```js
function showDetails(id) {
  const update = () => renderDetails(id);
  if (!document.startViewTransition) return update();
  document.startViewTransition(update);
}
```

## Controls

- preserve semantic navigation, focus management, heading announcement, and URL/history behavior independently of animation;
- respect reduced-motion preferences by shortening or disabling nonessential transition animation;
- give unique `view-transition-name` values only to intended elements;
- avoid extending a transition around network work; update known DOM state and render loading/error UI normally;
- for MPAs, opt in on both same-origin documents and preserve normal navigation as fallback.

## Verification

- unsupported browsers complete the update/navigation with no JavaScript error;
- keyboard focus lands on the appropriate new content;
- screen-reader announcements are not duplicated or suppressed;
- reduced-motion testing has no disorienting animation;
- rapid navigation, failed updates, and back/forward restore an intelligible state.

## Gotchas

- Cross-document transitions require same-origin documents.
- The old snapshot is not interactive UI; do not treat it as live state.
- `skipTransition()` skips animation, not the update callback.
- Animation smoothness is not a substitute for loading, error, or focus handling.

## Related

- `frontend/html-accessibility-aria.md`
- `frontend/react-router-patterns.md`
- `frontend/css-animation-performance.md`
