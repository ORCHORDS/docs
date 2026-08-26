# scroll-driven-animations

**Issue:** Scroll-linked effects — reading-progress bars, reveal-on-scroll, parallax, sticky-section transitions — have historically been built with JavaScript scroll event listeners plus requestAnimationFrame. That design fights the browser: scroll events fire on the main thread at high frequency, every handler reads layout geometry (triggering layout thrashing), and frames drop whenever the main thread is busy, producing the classic jank where the animated layer lags behind the scroll position. CSS scroll-driven animations (the scroll() and view() timeline types) move these effects to the compositor thread, letting the browser drive the animation directly from scroll offset without dispatching events or running script per frame. Chrome shipped it in 115, Safari 26 shipped it in 2025, and Firefox has been converging on it under the Interop 2025 effort, making 2025-2026 the practical migration window.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The scroll-handler performance problem

1. **Scroll events are main-thread and bursty.** Handlers can fire dozens of times per second during a flick gesture; each callback competes with input processing, rendering, and application logic on the same thread.

2. **Every read of geometry forces layout.** Typical handlers call getBoundingClientRect or read scrollTop and then mutate styles, interleaving forced synchronous layout with writes — the textbook layout-thrashing loop that scales badly with DOM size.

3. **JS-driven effects can never be frame-synced reliably.** Even with requestAnimationFrame, the script runs after scroll update, so the painted position lags by at least a frame on busy pages. Users perceive this as rubber-banding or flicker on mid-range mobile devices.

4. **The cost is recurring, not one-time.** Unlike a slow page load, scroll jank taxes every second of every visit and directly harms INP-adjacent responsiveness because scroll handlers occupy the main thread user input needs.

## The CSS primitive set

1. **scroll() timelines map animation progress to scroll position.** Declaring animation-timeline with a scroll() function (or a named scroll-timeline on a scroller) makes keyframe progress a direct function of how far the container has scrolled — the reading-progress bar becomes a five-line declaration with no listener.

2. **view() timelines map to element visibility.** A view() timeline (or named view-timeline) animates an element through the phases of its passage through the viewport, replacing most reveal-on-scroll IntersectionObserver code for animation-only use cases.

3. **Named timelines decouple scroller and target.** Defining scroll-timeline-name or view-timeline-name on the scroller/subject and referencing it via timeline-scope lets elements outside the scroller animate from its scroll, which covers headers, progress indicators, and sticky toolbars.

4. **Standard keyframes drive everything.** The animations use ordinary @keyframes and animation properties, so transforms and opacity defined once work under both scroll-driven and time-driven control — easing and animation-range tune how scroll distance maps to progress.

## Performance characteristics

1. **Compositor-thread execution.** Animations limited to transform and opacity can run on the compositor, decoupled from main-thread congestion. Even with other properties, the browser interpolates from scroll offset without dispatching scroll events, eliminating the handler cost entirely.

2. **No layout reads in the hot path.** The browser resolves the scroll-to-progress mapping internally without forced synchronous layout, removing the read-write thrash that plagued handler-based implementations.

3. **Frame-perfect synchronization.** Because the compositor owns both scroll offset and animation state, the rendered position updates in the same frame as the scroll — the visual lag class disappears rather than being mitigated.

4. **Main-thread interference still matters at setup.** Timeline ranges are resolved when styles/layout compute; extremely deep DOM or heavy style recalculation shifts the cost to layout time, so containment (css containment, content-visibility) remains relevant for long scroll containers.

## Progressive enhancement and support

1. **Feature-detect, do not user-agent sniff.** Wrap scroll-driven styles in @supports (animation-timeline: scroll()) and keep the JS fallback path for engines where it is disabled; Chromium and Safari 26 take the native path, others fall back unchanged.

2. **Prefer native-only when the effect is decorative.** For progress bars and reveals, an engine without support simply shows static (or final-state) content — often a better experience than shipping a JS fallback that janks. Make "no animation" an accepted degradation on the tail of support.

3. **Audit the fallback for interaction-only observers.** If IntersectionObserver code exists solely to trigger animations, gate its registration on the same @supports check (via CSS.supports in JS) so capable browsers never load the observer path at all.

4. **Track field support, not just caniuse.** Enterprise fleets and older iOS devices lag browser releases. Measure the share of traffic taking the fallback path via a CSS.supports beacon before deleting the JavaScript entirely.

## Patterns worth standardizing

1. **Reading progress and scroll shadows.** A scroll()-driven scaleX transform on a fixed bar replaces the most ubiquitous scroll listener on the web; the same pattern drives dynamic table headers and shadow fades with zero script.

2. **Reveal-on-scroll without observers.** view() timelines with animation-range cover fade/slide-in reveals declaratively, and unlike observer-based reveals they run backwards smoothly when the user scrolls up.

3. **Parallax that does not jank.** Layered elements with different scroll() ranges produce parallax whose cost is bounded by compositor work, not handler frequency — the flagship case where the JS version was worst.

4. **Scroll-snap galleries and sticky storytelling.** Combining scroll-snap containers with view() driven crossfades enables image-sequence and section-transition effects that previously required scroll hijacking or libraries — remove those libraries and their bundles when migrating.
