# view-transitions-api-performance

**Issue:** The View Transitions API (same-document transitions via document.startViewTransition and cross-document transitions for MPAs) makes it trivially easy to add animated transitions between UI states, and frameworks from React to Svelte now wrap it. The trap is that the API's convenience hides a two-phase cost model: capturing live snapshots of the old and new DOM happens on the main thread and can freeze interaction for tens or hundreds of milliseconds on large subtrees, while the resulting animation runs compositor-side and is nearly free. Teams that sprinkle view-transition-name across whole page containers get janky, INP-hostile transitions that feel worse than no transition at all. Using the API well requires deliberately keeping the captured subtree small and the animated properties compositor-friendly.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How the cost model works

1. **Capture is main-thread.** When a transition starts, the browser takes a visual snapshot (effectively a rasterized capture) of every element carrying a view-transition-name, both before and after the DOM change. This capture plus the forced style/layout pass happens synchronously on the main thread, so a large named subtree directly translates into blocked input and long tasks.
2. **Animation is compositor-side.** Once captured, the pseudo-element tree (::view-transition-group, ::view-transition-image-pair, ::view-transition-old/new) animates transform and opacity on the compositor, off the main thread. The animation phase is generally not the bottleneck; the capture phase is.
3. **The update callback runs inside the transition.** The DOM mutation you pass to startViewTransition executes between the two captures, so slow component rendering (data fetches resolved inside the callback, heavy reconciliation) is billed to the transition and extends the frozen window. The WICG explainer is explicit that the promise settling gates the transition finishing.

## Rules for keeping transitions fast

1. **Name as few elements as possible.** Apply view-transition-name only to the specific hero elements that should visually persist (an avatar, a card, a header), never to body, main, or whole route containers. Every additional named element adds a capture cost and an extra compositor layer.
2. **Animate only transform and opacity.** Custom ::view-transition-group animations that touch width, height, top, or box-shadow force layout or paint work per frame. Encode size changes as scale transforms to stay on the compositor.
3. **Keep the update callback lean.** Do data fetching before calling startViewTransition and pass a callback that only swaps DOM. If the new view is not ready, either delay starting the transition or use a placeholder element that carries the transition while content streams in behind it.
4. **Batch shared styles with view-transition-class.** Instead of duplicating animation CSS per named element, assign a view-transition-class and style the group once; this keeps stylesheets small and avoids per-element rule matching during the critical capture window.
5. **Respect reduced motion.** Gate transitions behind a prefers-reduced-motion check. Users who opt out skip the capture cost entirely, which is both an accessibility win and a main-thread saving for the cohort that needs it most.

## Same-document vs cross-document differences

1. **SPA same-document transitions.** With document.startViewTransition you control timing manually, which means you can pre-warm data and choose the cheapest moment to capture. The risk is calling it on every route change; consider skipping transitions for keyboard-driven rapid navigation where users want instant response over polish.
2. **MPA cross-document transitions.** Cross-document transitions (opt-in via a meta tag and CSS, same-origin only) snapshot the outgoing page before navigation, so the outgoing page's complexity is the cost driver. Keep the named elements on your most-trafficked outgoing templates small, and remember cross-document transitions do not run for BFCache restores in all engines.
3. **Framework wrappers add overhead.** React's unstable_ViewTransition and Next.js wrappers diff and coordinate with concurrent rendering; verify with a Performance panel recording that the wrapper is not deferring the update callback into a long task of its own.

## Diagnosing janky transitions

1. **Record a trace per transition.** In Chrome DevTools Performance panel, record a click that triggers the transition and look for the long task spanning ViewTransition capture; if the "Run ViewTransition" long task exceeds roughly 50 ms, reduce named elements or move work out of the callback.
2. **Watch INP attribution.** If your INP attributions cluster on the transition trigger and point at style/layout within the capture, that is direct evidence the named subtree is too big. The LoAF (Long Animation Frames API) entry will show the culprit script and duration.
3. **Test on low-end hardware.** Capture cost scales with raster area and device pixel ratio; a transition that is imperceptible on a desktop may freeze a budget phone for 200+ ms. Profile on your actual low-end target, not a dev machine.

## When not to use it

1. **High-frequency interactions.** Hover states, rapid list filtering, and drag interactions should use plain CSS transitions on composited properties; full View Transitions capture semantics are wasted overhead there.
2. **Content that changes faster than the animation.** If the new view streams in progressively (skeletons then data), a single snapshot pair misrepresents the final state; either transition the skeleton only or skip the API for that view.
