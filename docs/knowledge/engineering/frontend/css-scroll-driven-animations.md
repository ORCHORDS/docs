# CSS Scroll-Driven Animations

## Symptom

You want a header that shrinks on scroll, a progress bar that tracks reading
position, or a parallax background. The classic approach is a `scroll` event
listener with `requestAnimationFrame`, fighting passive-listener warnings and
jank on mobile. The scroll handler runs on the main thread, so a heavy page
drops frames exactly when the user is scrolling.

CSS Scroll-Driven Animations (Baseline widely available in 2026) let you
drive an animation's timeline from scroll position — entirely off the main
thread, no JavaScript.

## Basic usage

```css
@keyframes shrink-header {
  from { height: 80px; background: transparent; }
  to   { height: 56px; background: var(--surface); }
}

.header {
  animation: shrink-header linear;
  animation-timeline: scroll(root block);  /* tied to document scroll */
  animation-range: 0 120px;                 /* run over first 120px of scroll */
}
```

### Reading progress bar

```css
.progress-bar {
  transform-origin: left;
  animation: grow linear;
  animation-timeline: scroll(root);
}

@keyframes grow {
  from { transform: scaleX(0); }
  to   { transform: scaleX(1); }
}
```

### Element-visibility-driven animation

```css
.feature-card {
  animation: fade-up linear both;
  animation-timeline: view();
  animation-range: entry 0% cover 40%;
}

@keyframes fade-up {
  from { opacity: 0; transform: translateY(40px); }
  to   { opacity: 1; transform: translateY(0); }
}
```

`view()` ties the timeline to when the element enters the scrollport, giving
you scroll-triggered reveal animations without `IntersectionObserver`.

## Gotchas

### `scroll()` vs `view()` — pick by what drives the animation

- `scroll()` — the timeline tracks the scroll position of a container. Use
  for page-wide effects (sticky header, progress bar).
- `view()` — the timeline tracks a specific element's visibility in the
  scrollport. Use for reveal-on-scroll of individual elements.

Mixing them up gives animations that fire at the wrong scroll offsets.

### `animation-range` defaults can surprise you

With `view()`, the default range is `entry 0% entry 100%` — the animation
completes as soon as the element is fully in view. If you want the animation
to continue as the element passes through the viewport center, you must set
`animation-range: entry cover` or `cover 0% cover 100%`.

### Not all animation properties can be driven this way

Scroll-driven timelines work with any property you can animate with
`@keyframes` (transform, opacity, clip-path, etc.). They do NOT work with
custom property animations unless those properties are registered with
`@property` as `<length>` or similar typed values.

```css
@property --bar-width {
  syntax: '<length>';
  inherits: false;
  initial-value: 0px;
}
```

### No `prefers-reduced-motion` exception by default

Scroll-driven animations run even when the user has requested reduced motion.
You must opt out explicitly:

```css
@media (prefers-reduced-motion: reduce) {
  * {
    animation-timeline: auto;  /* or unset */
    animation: none;
  }
}
```

Forgetting this is an accessibility regression — scroll-driven movement can
trigger motion sensitivity exactly when the user is scrolling.

### Browser support: progressive enhance

```css
.progress-bar {
  width: 100%; /* fallback: full bar always visible */
}

@supports (animation-timeline: scroll()) {
  .progress-bar {
    width: auto;
    animation: grow linear;
    animation-timeline: scroll(root);
  }
}
```

Without the fallback, users on older browsers see a broken (empty or stuck)
progress bar.

### `root` vs named containers

`scroll(root)` tracks the document scroller. For a scrollable sub-region
(chat panel, carousel), give the container `scroll-timeline-name`:

```css
.chat-panel {
  scroll-timeline-name: --chat-scroll;
}

.chat-panel .pulse {
  animation-timeline: --chat-scroll;
}
```

### Performance: still avoid animating layout properties

Even off-main-thread, animating `width` or `top` triggers layout. Prefer
`transform` and `opacity` — these are compositor-only and stay smooth.
