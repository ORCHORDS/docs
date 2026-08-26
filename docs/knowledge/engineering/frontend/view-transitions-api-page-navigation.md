# View Transitions API — Smooth Page Navigation in SPAs and MPAs

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your SPA page transitions are jarring — content pops in instantly with
no visual continuity between routes. You tried CSS animations and
GSAP/Framer Motion for transitions, but coordinating old-page-out and
new-page-in animations with data fetching and DOM updates is fragile.
Your MPA has no transitions at all — every navigation is a full page
load with a white flash. Users perceive the app as slow even though
page loads are under 500ms, because there is no visual feedback during
the transition.

## Context

The View Transitions API is a browser-native mechanism for animating
DOM changes during navigation or state updates. It captures bitmap
snapshots of the old and new states, then cross-fades (or custom-
animates) between them. It works for both SPAs (same-document
transitions via `document.startViewTransition()`) and MPAs (cross-
document transitions via the CSS `@view-transition` rule). As of 2026,
same-document transitions have broad support (Chrome 111+, Edge 111+,
Safari 18+, Firefox 133+). Cross-document MPA transitions are supported
in Chrome 126+, Edge 126+, and Safari 18.2+. Firefox MPA support
remains behind a flag.

## Same-document transitions (SPA)

```javascript
// Basic SPA view transition
document.startViewTransition(() => {
  updateContent(newData);
});

// With async operations (data fetching)
document.startViewTransition(async () => {
  const data = await fetchNewPageData();
  document.querySelector('.content').innerHTML = data;
});

// With transition lifecycle
const transition = document.startViewTransition(async () => {
  await updateDOM();
});

// Wait for animation to complete
await transition.finished;

// React Router integration
import { useNavigate } from 'react-router-dom';

function NavLink({ to, children }) {
  const navigate = useNavigate();

  const handleClick = (e) => {
    e.preventDefault();
    if (!document.startViewTransition) {
      navigate(to);
      return;
    }
    document.startViewTransition(() => navigate(to));
  };

  return <a href={to} onClick={handleClick}>{children}</a>;
}
```

## Cross-document transitions (MPA)

```css
/* Both source and destination pages must include this */
@view-transition {
  navigation: auto;
}
```

## Named transitions

```css
/* Give elements unique transition names */
.hero-image { view-transition-name: hero; }
.page-title { view-transition-name: title; }
.card-thumbnail { view-transition-name: card-thumb; }

/* Customize animation for specific elements */
::view-transition-old(hero) {
  animation: slide-out 0.3s ease-in;
}
::view-transition-new(hero) {
  animation: slide-in 0.3s ease-out;
}

/* Default root cross-fade */
::view-transition-old(root) {
  animation: fade-out 0.2s;
}
::view-transition-new(root) {
  animation: fade-in 0.2s;
}

/* Reduce motion for accessibility */
@media (prefers-reduced-motion: reduce) {
  ::view-transition-group(*),
  ::view-transition-old(*),
  ::view-transition-new(*) {
    animation: none !important;
  }
}
```

## Browser support (2026)

```
Same-document (SPA):
  Chrome 111+    ✓
  Edge 111+      ✓
  Safari 18+     ✓
  Firefox 133+   ✓

Cross-document (MPA):
  Chrome 126+    ✓
  Edge 126+      ✓
  Safari 18.2+   ✓
  Firefox         Behind flag

Progressive enhancement:
  if (!document.startViewTransition) {
    // Fallback: update DOM directly, no animation
    updateDOM();
    return;
  }
  document.startViewTransition(() => updateDOM());
```

## Anti-patterns

- **Duplicate view-transition-name values** — if two rendered elements
  share the same `view-transition-name` at the same time,
  `ViewTransition.ready` rejects and the entire transition is skipped
  silently. Every name must be unique among simultaneously rendered
  elements.
- **Long transition animations** — the API captures bitmap snapshots
  and animates between them. During animation, the page is non-
  interactive. Keep transitions under 300ms to avoid blocking user
  interaction.
- **Not treating as progressive enhancement** — Firefox MPA support
  is still behind a flag. Always ensure the page works without
  transitions. Use feature detection before calling the API.
- **Animating everything** — applying transitions to every DOM
  change creates visual noise. Reserve transitions for meaningful
  navigation events (route changes, modal opens, list reorders),
  not every state update.

## Gotchas

- **Snapshots, not live DOM** — the API animates between bitmap
  snapshots of old and new states. During the animation, you are
  looking at images, not interactive DOM elements. Clicks during
  a transition do not reach the elements being animated.
- **CSS containment requirement** — elements with `view-transition-
  name` should have CSS containment (`contain: layout` or
  `contain: paint`) for the API to correctly capture dimensions
  and position.
- **Cross-origin limitation** — cross-document transitions only work
  for same-origin navigations. Cross-origin navigations silently
  fall back to standard navigation with no error.
- **Dynamic view-transition-name for lists** — for list items that
  transition individually (e.g., card grids), generate unique names
  per item (e.g., `view-transition-name: card-${id}`). This requires
  inline styles or CSS-in-JS since CSS cannot interpolate.

## Verification

- Transitions work on supported browsers and degrade gracefully.
- `prefers-reduced-motion` is respected with animation disabled.
- No duplicate `view-transition-name` values exist simultaneously.
- Transition duration is under 300ms for interactive pages.
- Feature detection is used before calling the API.
- Cross-document transitions opt in on both source and destination.

## Related

- `documentation/docs/policies/frontend/micro-frontends-module-federation.md`
- `documentation/docs/policies/performance/critical-rendering-path-css-optimization.md`
- `documentation/docs/policies/frontend/react-server-components-streaming-ssr.md`

## Source URLs (verified 2026-08-16)

- Smooth Transitions with the View Transition API — https://developer.chrome.com/docs/web-platform/view-transitions
- Using the View Transition API — MDN — https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API/Using
- Cross-Document View Transitions: The Gotchas Nobody Mentions — https://css-tricks.com/cross-document-view-transitions-part-1/
- Cross-Document View Transitions Are Finally Cross-Browser (2026) — https://trade-assistance.com/blog/cross-document-view-transitions-mpa-2026/
