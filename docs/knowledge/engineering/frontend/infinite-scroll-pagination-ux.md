# infinite-scroll-pagination-ux

**Issue:** Infinite scroll feels simple but couples three hard problems: a loading trigger (IntersectionObserver sentinel vs scroll listeners), a server pagination model (cursor vs offset), and a UX contract (footer access, back-navigation scroll restoration, find-in-page, accessibility). Done wrong it produces duplicate rows from racing fetches, skipped items when new content inserts mid-scroll, lost scroll positions on back navigation, and a page that can never reach its own footer. Choosing infinite scroll at all is itself a product decision — feeds and browse surfaces suit it; e-commerce search and task-list surfaces usually want explicit pagination.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Choosing the pagination model

1. **Use cursor pagination for infinite scroll, not offset.** Offset paging (skip=20&limit=20) skips or duplicates rows when items are inserted or deleted between fetches — a social feed that inserts new posts at the top while the user scrolls guarantees duplicates with offsets. A cursor (opaque "fetch items after this id/timestamp") is stable under insertion, which is why every feed-style API converges on it.
2. **Treat cursors as opaque strings.** Do not parse, sort, or reuse cursor internals client-side; the server encodes its ordering snapshot inside them. Persist the cursor per list instance, not in a shared module variable, so two lists on one page cannot steal each other's position.
3. **Offset paging only for small, static admin-style sets.** Jump-to-page, stable total counts, and data that does not mutate mid-browse (a paginated back-office table) is where classic page numbers still win, and where UI affordances like page links are worth their cost.
4. **Require an end signal from the API.** The list needs to know it is done (empty page, `nextCursor: null`, total reached). Without an end signal the sentinel refires forever, generating infinite no-op requests against the server and masking real empty states.

## The loading trigger

1. **Use an IntersectionObserver on a sentinel element, never scroll listeners.** Scroll handlers run on the main thread every frame and read layout properties that force reflow; the observer offloads hit-testing to the browser. Observe a dedicated empty div placed after the list, with `rootMargin` (e.g. 400px) so loading starts before the user hits the bottom — perceived speed comes from prefetching the next batch.
2. **Guard against duplicate fetches when the sentinel re-enters view.** The observer fires repeatedly while the sentinel is visible; without an in-flight flag (or an abort-and-replace strategy) you get double fetches and duplicated rows. This is the single most common infinite-scroll bug in review queues.
3. **Load on mount if the first screen does not fill the viewport.** If the initial page returns 3 items and the sentinel is already visible, the observer may or may not re-fire depending on timing — explicitly check "is the sentinel visible and idle?" after the first page resolves.
4. **Prefer TanStack Query's `useInfiniteQuery` over hand-rolled loaders.** It owns the page cache, the `fetchNextPage` in-flight state, `hasNextPage`, `isFetchNextPageError`, deduplication, and retry semantics; hand-rolled versions reimplement all of it with more bugs. `swr`-based equivalents exist; the point is not to write the state machine by hand.
5. **Handle the failure path visibly.** When the next page fails, show a "Load failed — Retry" affordance at the list tail; a silent failure looks like the end of the list and users read it as "that's all there is".

## UX, state, and accessibility

1. **Preserve scroll position on back-navigation.** Navigating item -> back should land where the user left. Options: cache the list (query cache with long staleTime) plus browser scroll restoration, or persist scroll offset and cursors in session state/URL. The naive refetch-from-page-one approach is why users hate infinite scroll on news sites.
2. **Encode position in the URL for shareable states.** At minimum `?page=` or a cursor token for deep links and refresh; infinite scroll that resets to the top on every refresh breaks sharing and the browser's own back/forward expectations.
3. **Keep the footer reachable.** Infinite scroll can make the site footer permanently unreachable — either render the footer in a sidebar/portal, or stop auto-loading after N pages and switch to a "Show more" button (the pattern e-commerce converged on to satisfy both browse flow and footer/legal-link access).
4. **Announce loading and completion to assistive tech.** New items appended to a live region should be announced once ("Loaded 20 more posts"), and the end state made explicit ("End of results") — otherwise screen-reader users face a silently growing list with no signal it ended.
5. **Respect find-in-page and jump-to-top.** Documented infinite-scroll weaknesses: browser Ctrl+F only searches rendered DOM, so train users with an in-app search instead; and provide an explicit "back to top" control once the DOM grows past a few thousand nodes.
6. **Virtualize long sessions.** Hours of scrolling accumulate thousands of DOM nodes and degrade INP. Cap rendered rows with a virtualizer (see the react-virtual-list article) once the list can exceed ~500-1000 items; the sentinel pattern composes cleanly with windowing because both operate on the logical list, not the DOM.

## Product-fit decision checklist

1. **Feeds and discovery: infinite scroll wins.** Goal-less browsing, mobile-thumb ergonomics, and recency-ordered content fit continuous loading with cursors.
2. **Search results and catalogs: prefer pagination or load-more.** Users have a target, need result counts, compare positions, and need the footer (filters, trust links). "Load more" buttons are the compromise that keeps user control while avoiding page-number maintenance.
3. **Task lists and inboxes: pagination or grouping.** Unbounded scroll in an inbox trains users they are never done; finite pages make "inbox zero" legible.
4. **Mobile web specifically: guard the address bar.** Address-bar show/hide changes viewport height and can retrigger the sentinel; use `100dvh`-aware heights and rootMargin tuned on device, and test on real iOS Safari — IntersectionObserver timing differs there from desktop Chrome.
