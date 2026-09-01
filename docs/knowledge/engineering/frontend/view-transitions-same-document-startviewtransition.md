# View Transitions Same-Document StartViewTransition Orchestration

## Scope

Orchestrating same-document view transitions through `document.startViewTransition()` and the `ViewTransition` object it returns — callback timing (`updateCallbackDone`, `ready`, `finished`), `skipTransition()`, snapshot capture semantics, `view-transition-name` uniqueness, pseudo-element animation customization, and integrating framework renders into the callback without breaking async updates. Excludes cross-document (`@view-transition`) navigation transitions, which have a separate article, and excludes the accessibility of reduced-motion policy beyond its direct interaction with this API.

## Workflow or implementation guidance

`startViewTransition` runs your DOM mutation inside a browser-managed frame choreography. The contract to internalize is the ordering: the old state is snapshotted, your callback applies the new DOM, the new state is captured, pseudo-elements animate between the two, and the page is live again when the animation settles. The `ViewTransition` object exposes each phase as a promise:

```js
const vt = document.startViewTransition(async () => {
  await router.navigate('/items/42');   // swap the DOM here
});

vt.updateCallbackDone.then(() => console.log('DOM updated, new snapshot queued'));
vt.ready.then(() => console.log('pseudo-tree built, animations started'));
vt.finished.finally(() => console.log('transition fully settled or skipped'));
```

`updateCallbackDone` resolves when your callback finishes (or rejects with its exception — the DOM update is your code's failure domain). `ready` resolves once the new snapshot is captured and the animation is playable; it rejects if pseudo-tree construction fails — the canonical cause being a duplicate `view-transition-name`. `finished` resolves when animations end or the transition is skipped, after the pseudo-elements are gone and the real DOM is interactive again. Anything user-facing that must not be blocked belongs after `finished`; anything that must happen while the snapshots still cover the screen belongs after `ready`.

Unique names are the hard constraint. Every element with a `view-transition-name` forms its own captured pair (`::view-transition-old(name)` / `::view-transition-new(name)`); two rendered elements sharing one name at capture time aborts the pseudo-tree build, `ready` rejects, and the browser falls back to an instant swap. List grids need generated names:

```js
for (const card of grid.children) {
  card.style.viewTransitionName = `card-${card.dataset.id}`;
}
```

Names must be set before the transition captures and cleared only when the element genuinely leaves the matched set — stale inline names from a removed element are the usual source of the duplicate error in long-lived singletons.

Customizing motion is pure CSS against the pseudo-tree. The group pseudo handles geometry and stacking; the image pseudos carry the snapshots:

```css
::view-transition-old(hero) { animation: 220ms ease-in both fade-and-slide-out; }
::view-transition-new(hero) { animation: 220ms ease-out 80ms both fade-and-slide-in; }

@media (prefers-reduced-motion: reduce) {
  ::view-transition-group(*), ::view-transition-image-pair(*),
  ::view-transition-old(*), ::view-transition-new(*) {
    animation: none !important;
  }
}
```

Framework integration has one rule: the callback must leave the DOM in the final state when it resolves. With React, awaiting a state flush (for example an await on the render commit via `flushSync`-wrapped updates or a framework-equivalent) keeps the new snapshot from capturing a half-updated tree — a transition that animates to stale content is almost always an unawaited render. Data fetching goes inside the callback too: the old snapshot stays on screen while data loads, which is precisely the loading-state replacement this API offers, at the cost of the page being non-interactive for the fetch duration. Long awaits need a guard:

```js
const vt = document.startViewTransition(() => loadAndRender(id));
setTimeout(() => { if (!vt.finished.done) vt.skipTransition(); }, 400);
```

`skipTransition()` aborts the animation and jumps to the end state — the DOM update still applies, only the animation is dropped. Use it for deadline enforcement and for `prefers-reduced-motion` policies implemented in JS rather than CSS.

## Controls

- One `view-transition-name` per captured element per capture; generated per-item names for grids, set before the call, cleaned when items unmount.
- `ready` guarded with rejection handling; a rejected `ready` (duplicate name) should log loudly in dev, because the fallback is a silent instant swap.
- Time-box async callbacks (a `skipTransition` timer) so a slow fetch degrades to a normal update instead of freezing the UI behind snapshots.
- Wrap every `startViewTransition` call in `if (!document.startViewTransition) { update(); return; }` — the enhanced path and the plain path must produce identical DOM.
- Reduced-motion CSS zeroing the pseudo-element animations (or `skipTransition` in JS) as a first-class requirement, not an afterthought.

## Validation evidence

- Promise-ordering unit test on a fixture page: log resolution order of `updateCallbackDone` → `ready` → `finished` and assert the sequence holds for a synchronous and an async callback.
- Duplicate-name repro test: intentionally set two elements to the same name, assert `ready` rejects with `AbortError`-family error and the DOM still reaches the new state via `finished`.
- Interaction test during animation: assert clicks on the destination element land once `finished` resolves and never during the animation window, documenting the snapshot-interactivity boundary for the team.
- Reduced-motion test with `prefers-reduced-motion: emulate` in the browser test runner: assert zero animation frames are produced for the pseudo-tree while the DOM update still completes.
- Visual regression screenshots at animation midpoint and end for each named transition, per viewport breakpoint.

## Failure modes and correction

- `ready` rejects, transition silently becomes an instant swap: duplicate `view-transition-name` at capture time. Audit for leaked inline names (grid items that unmounted without clearing `style.viewTransitionName`) and dynamic singletons re-rendered with the old name still applied.
- Transition animates to the old content: the callback resolved before the framework committed — await the render (or wrap the update synchronously) so the new snapshot captures the final DOM.
- Page feels frozen on slow data: the callback is awaiting a network call behind snapshots. Move the fetch ahead of the transition, shrink the awaited work to the DOM swap, or add the skip timer.
- Animations replay from the wrong position for elements that resize: snapshot pairs animate the old and new images with the group geometry morphing between the two boxes; large size deltas stretch the bitmap — give the element `contain: paint` or accept the stretch by design.
- Transitions nest badly when two features call `startViewTransition` simultaneously: only one transition runs at a time per document — the second call while one is active finishes the first's phases immediately. Serialize transitions through a small queue keyed by feature.
- `finished` never resolves: an animation that never ends (infinite animation on a pseudo-element). Use finite `animation-fill-mode: both` keyframes.

## Limitations

- Snapshots are bitmaps: mid-animation content is not live, focus lands on the real DOM only after settle, and CSS resolution (hover states, typed OM values) does not apply to pseudo-images.
- The callback's DOM update is all-or-nothing with the transition; partial-state intermediates cannot be staged across multiple captured frames in one call.
- Elements inside cross-origin iframes and some replaced elements are not capturable; they appear as empty regions in the snapshot.
- Performance scales with the number of named elements and surface area; every name adds a pair of texture captures and a composited layer, so name sparingly.
- The `types` mechanism for per-transition-type styling requires passing options and selecting with `:active-view-transition-type()` — supported in the same-document case but version-dependent across engines; feature-detect before relying on it.

## Canonical sources

- W3C CSS Working Group, CSS View Transitions Module Level 1: https://www.w3.org/TR/css-view-transitions-1/
- MDN, `ViewTransition`: https://developer.mozilla.org/en-US/docs/Web/API/ViewTransition
- HTML Standard, `document.startViewTransition`: https://html.spec.whatwg.org/multipage/nav-history-apis.html#dom-document-startviewtransition
