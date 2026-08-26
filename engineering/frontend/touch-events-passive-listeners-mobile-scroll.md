# touch-events-passive-listeners-mobile-scroll

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

The anonymous feed scrolls at 30 fps or lower on mid-range Android
(Snapdragon 680-class). Chrome DevTools Performance timeline shows
long tasks on the main thread during scroll. Lighthouse flags "Does
not use passive listeners to improve scrolling performance" with the
feed container as the offending element. Swipe-to-dismiss and
pull-to-refresh handlers are the proximate cause.

## Context

example project runs an anonymous social feed with infinite scroll that
must sustain 60 fps on mid-range Android. The feed container
attaches `touchstart`/`touchmove` listeners for custom gestures.
Without `{ passive: true }`, the browser's scroll compositor stalls
waiting for those listeners to return. The fix combines passive
listener options, `touch-action` CSS, and native DOM attachment in
React instead of synthetic event props.

## Why non-passive listeners block scroll

When `touchstart` or `touchmove` fires, the browser cannot know
in advance whether JavaScript will call `preventDefault()` to cancel
native scroll. It must wait for the listener to finish before
committing the next scroll frame — a stall of 10–50 ms on a
mid-range device, enough to drop frames visibly.

```
touchstart fires
  → compositor queues scroll frame
  → main thread runs listener (10–50 ms)
  → compositor finally commits frame   ← visible jank
```

Chrome 56+ (2017) made `touchstart`, `touchmove`, and `wheel`
passive by default at `window`, `document`, and `document.body`.
Listeners on **any other element** — including a feed `<div>` —
still default to `{ passive: false }` and continue to block. The
Lighthouse audit fires for these element-level cases regardless
of the browser-level change.

## The `{ passive: true }` option

Pass `{ passive: true }` as the third argument to tell the browser
the listener will never call `preventDefault()`. The compositor
can then scroll immediately on a background thread; any
`preventDefault()` call inside the listener is silently ignored.

```js
// Blocks compositor until handler returns
el.addEventListener('touchmove', handleSwipe);

// Compositor scrolls immediately; handler runs concurrently
el.addEventListener('touchmove', handleSwipe, { passive: true });
```

Supported since Chrome 51 / Firefox 49 / Safari 10 (2016). No
feature-detection fallback is needed for any device in the example project
target matrix.

## `touch-action` CSS — the correct way to suppress scroll

`touch-action` tells the browser which gestures it handles natively,
before event dispatch, without any compositor stall. Use it instead
of `preventDefault()` to constrain scroll in a region.

```css
/* Disable all browser touch handling for gesture surfaces */
.gesture-surface   { touch-action: none; }

/* Vertical scroll only — horizontal swipe fires as pointer event */
.feed-container    { touch-action: pan-y; }

/* Horizontal swipe only — vertical scroll blocked */
.carousel-track    { touch-action: pan-x; }
```

For the example project feed: `touch-action: pan-y` on the scroll
container plus `{ passive: true }` on all listeners. Native
vertical scroll is never impeded; horizontal swipe-to-dismiss still
fires and can be measured without calling `preventDefault()`.

`touch-action` is fully supported in Chrome, Firefox, Edge, and
Safari 13+. Directional variants `pan-left` / `pan-right` / `pan-up`
/ `pan-down` are still experimental; use `pan-x` / `pan-y`.

## Touch Events vs Pointer Events

Prefer Pointer Events for new gesture code. They unify touch,
mouse, and stylus into one handler, expose `pointerId` for
multi-touch, and support `setPointerCapture` for reliable drag
(pointer stays captured even when it leaves the element). Passive
semantics are identical to Touch Events.

```js
el.addEventListener('pointerdown', (e) => {
  el.setPointerCapture(e.pointerId); // keeps gesture on this element
});
el.addEventListener('pointermove', handleSwipe, { passive: true });
el.addEventListener('pointerup', onEnd);
```

Touch Events are still appropriate when raw multi-touch contact
data from `changedTouches[]` is needed. On Firefox for Android,
Pointer Events are the primary API with Touch Events present but
less tested for passive defaults — another reason to prefer
`pointerdown` / `pointermove` / `pointerup` for new code.

## iOS Safari rubber-band scroll and `overflow: hidden`

`overflow: hidden` on `<body>` does not reliably suppress iOS
Safari elastic (rubber-band) overscroll. Use `overscroll-behavior`
on iOS 16+ or a position-fixed lock for older versions.

```css
/* Option 1 — Safari 16+ / iOS 16+ */
body { overscroll-behavior: none; }

/* Option 2 — iOS 13–15 fallback (position-fixed lock) */
body.scroll-locked {
  position: fixed;
  width: 100%;
  overflow-y: scroll; /* prevents layout-shift from missing scrollbar */
}
```

Option 2 resets `window.scrollY`; save and restore it in JS:

```js
let savedY = 0;
const lockScroll = () => {
  savedY = window.scrollY;
  document.body.classList.add('scroll-locked');
  document.body.style.top = `-${savedY}px`;
};
const unlockScroll = () => {
  document.body.classList.remove('scroll-locked');
  document.body.style.top = '';
  window.scrollTo(0, savedY);
};
```

`-webkit-overflow-scrolling: touch` is deprecated since iOS 13;
modern iOS enables momentum scrolling natively on `overflow: auto`.

## React synthetic events and passive listeners

React attaches delegated listeners at the root (React 18: root
container; React 17: `document`). It registers them **non-passive**
to preserve `preventDefault()` support. An `onTouchMove` or
`onTouchStart` prop in JSX therefore blocks scroll via the delegated
root listener, even though the prop looks declarative and harmless.

The fix is native `addEventListener` inside `useEffect`:

```tsx
function FeedCard() {
  const ref = useRef<HTMLDivElement>(null);
  const handleMove = useCallback((e: TouchEvent) => {
    /* gesture math — never calls preventDefault() */
  }, []);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.addEventListener('touchmove', handleMove, { passive: true });
    return () => el.removeEventListener('touchmove', handleMove);
  }, [handleMove]);

  return <div ref={ref} style={{ touchAction: 'pan-y' }} />;
}
```

`e.nativeEvent` inside a React synthetic handler exposes the raw
DOM event but cannot lift the passive constraint already set at
root delegation — it does not help.

## Anti-patterns

- Using `onTouchMove` / `onTouchStart` React props on scroll
  containers — non-passive root delegation stalls the compositor.
- Calling `e.preventDefault()` inside `touchmove` to suppress
  scroll — use `touch-action` CSS instead.
- `touch-action: none` on the entire feed or `<body>` — kills
  pinch-zoom and rubber-band globally.
- Attaching new `addEventListener` calls on every React render
  without `useEffect` cleanup — leaks listeners with session time.
- Omitting `{ passive: true }` on element-level listeners when
  `preventDefault()` is never called — the browser cannot infer
  this; the stall is unconditional.

## Gotchas

- Chrome passive defaults (window / document / body) do not extend
  to arbitrary `<div>` scroll containers. Lighthouse reliably
  catches element-level violations.
- `touch-action` is not CSS-inherited; a parent `touch-action: none`
  cannot be overridden in children. Set it as close to the gesture
  target as possible.
- Calling `preventDefault()` inside a passive listener is a no-op
  — it emits a console warning, does not block scroll, and does
  not throw. Easy to miss in tests.
- `useCallback` must produce a stable reference before `useEffect`
  attaches it. An unstable callback causes the effect to briefly
  remove and re-add the listener on every render.

## Verification

- Chrome DevTools → Performance → record scroll on a real device →
  no long tasks (>50 ms) on the main thread during scroll.
- Lighthouse → "Does not use passive listeners" audit passes.
- DevTools → Elements → Computed → confirm `touch-action: pan-y`
  on the feed scroll container.
- `adb shell dumpsys SurfaceFlinger --latency` on Snapdragon 680:
  p99 frame time under 17 ms during continuous feed scroll.

## Related

- `documentation/categories/frontend/infinite-scroll-pagination-ux.md`
- `documentation/categories/frontend/react-virtual-list.md`
- `documentation/categories/frontend/css-animation-performance.md`
- `documentation/categories/frontend/html-web-vitals-inp.md`
- `documentation/categories/frontend/css-mobile-viewport-units-dvh-svh.md`

## Source URLs (verified 2026-08-17)

- https://developer.mozilla.org/en-US/docs/Web/API/EventTarget/addEventListener
- https://developer.mozilla.org/en-US/docs/Web/API/TouchEvent
- https://developer.mozilla.org/en-US/docs/Web/CSS/touch-action
- https://www.greadme.com/blog/best-practices/improve-scrolling-with-passive-event-listeners-complete-guide
- https://github.com/github/eslint-plugin-github/blob/main/docs/rules/require-passive-events.md
- https://www.bram.us/2016/05/02/prevent-overscroll-bounce-in-ios-mobilesafari-pure-css/
