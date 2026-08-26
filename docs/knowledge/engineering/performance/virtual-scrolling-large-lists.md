# virtual-scrolling-large-lists

**Issue:** Rendering thousands of DOM nodes for a long list or table grinds the main thread to a halt. Every scroll frame forces style, layout, paint, and composite work proportional to total node count, not viewport size, so a 10,000-row feed can drop to single-digit FPS while INP on taps inside the list climbs past the 200 ms "poor" threshold. The fix is windowing: render only the visible slice plus a small overscan, and position it inside a spacer element that preserves the full scroll height. This article covers when to virtualize, how to implement it without scroll jank, the native CSS alternative, and the pitfalls (variable heights, keyboard access, scrollbars, search-in-page) that make naive implementations regress UX while winning benchmarks.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## When to virtualize

1. **Count threshold.** Below roughly 200 simple items, virtualization usually costs more than it saves; the bookkeeping (scroll listeners, absolute positioning, recycled nodes) can exceed the render cost of the full list. Profile first with the Chrome Performance panel — look for long "Recalculate Style" and "Layout" tasks during scroll.
2. **Node complexity multiplier.** The threshold is really about total DOM nodes, not item count. Twenty items each rendering a card with 60 nested nodes is already 1,200 nodes; a debug utility that prints document.querySelectorAll('*').length on route change catches this earlier than user complaints.
3. **Interaction profile.** Lists that users scroll fast, type into (filters, command palettes), or tap quickly benefit most, because virtualization directly protects INP and scroll-linked long tasks. Footer-adjacent lists nobody touches can stay simple.
4. **Growth direction.** Virtualize when the dataset is unbounded (activity feeds, log viewers, chat history) even if it is small today. Retrofitting windowing into a component with established CSS and tests is far more expensive than starting with it.

## Implementation techniques

1. **Use TanStack Virtual for JS windowing.** It is headless and framework-agnostic (React, Vue, Solid, Svelte, vanilla), ships a tiny core, supports dynamic row measurement, horizontal and grid layouts, and window- or element-scrolled containers. Headless means you keep your own markup and styling instead of fighting a component library's DOM.
2. **Overscan modestly.** Render 3-5 items above and below the viewport so fast flicks show content instead of blank flashes. Overscan beyond ~10 rows re-introduces the render cost you removed; measure scroll velocity if you need adaptive values.
3. **Absolute positioning with a spacer.** The standard structure is a relatively positioned container whose height equals totalItems times estimated item height, with rendered items absolutely positioned at their computed offsets. Never use margin/padding tricks that force full-layout invalidation each frame.
4. **Measure, then stabilize heights.** For dynamic rows, render with an estimate, use ResizeObserver to capture real heights, and cache per-item measurements so re-scrolling does not re-measure. Height thrash (estimate, correct, shift) is the top cause of scroll jank in virtualized lists and shows up as CLS if it happens above the fold.
5. **Keep scroll handling passive and cheap.** Translate scroll offsets through requestAnimationFrame; never do synchronous DOM reads (offsetTop) and writes interleaved, which causes layout thrashing. Libraries batch this for you — hand-rolled versions must too.

## Common pitfalls

1. **Scrollbar lying.** With estimated heights, the thumb jumps as the browser learns real sizes. Mitigate by refining estimates from measured averages, and accept some inaccuracy on very heterogeneous lists; instant scroll-to-bottom shortcuts help users skip the problem entirely.
2. **Keyboard and screen-reader access.** Off-screen items do not exist in the DOM, so tab order and virtual cursor navigation break unless you implement roving tabindex or aria-setsize/aria-posinset attributes that describe the full list to assistive tech.
3. **Find-in-page breaks.** Ctrl+F cannot find text in nodes that are not rendered. For documentation-like content, prefer paginated "load more" over windowing; reserve virtualization for feeds and data grids where search is app-mediated.
4. **Browser find and anchor links.** Deep links to item N must scroll programmatically before that item exists. Implement scrollToIndex that renders the target window first, then scrolls, then corrects once real heights arrive.
5. **Sticky headers and transforms.** position: sticky inside a transformed spacer behaves inconsistently across browsers; move sticky chrome (group headers, column labels) outside the virtualized region.

## Native alternatives and complements

1. **content-visibility: auto.** Setting content-visibility: auto with contain-intrinsic-size on list items lets the browser skip rendering off-screen content without JavaScript. It is excellent for medium lists (hundreds of items) and article-heavy pages, but the nodes still exist in the DOM, so memory and style recalculation scale with total count — it does not replace windowing for tens of thousands of rows.
2. **contain-intrinsic-size accuracy.** Provide a close intrinsic size estimate; bad estimates cause scrollbar jumping and unexpected scroll anchoring, the same failure mode as JS virtualization but without per-item measurement to correct it.
3. **Hybrid strategy.** A pragmatic 2025-era pattern is content-visibility: auto for the initial page plus TanStack Virtual for the unbounded appended tail, combining zero-JS cost for static content with hard bounds for the growing region.

## Measuring the win

1. **DOM node budget.** Assert total node count in CI for key routes (for example, under 1,500) so a refactor that un-virtualizes a list fails the build rather than shipping.
2. **Scroll performance.** Record Performance traces while programmatically scrolling (mouse wheel simulation) before and after; compare longest frame and layout time. Target no frame over ~10 ms of main-thread work during steady scrolling.
3. **INP on list interactions.** Use RUM attribution to confirm taps and keypresses inside the list stay under 200 ms p75 after virtualization; windowing that shifts work to event handlers can paradoxically worsen INP if handlers re-render the whole window synchronously.
4. **Memory.** Check the Memory panel heap before/after — detached nodes from recycled rows without pooling can erase the GC pressure win.
