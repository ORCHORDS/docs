# data-table-virtualization-sorting-filtering

**Issue:** Admin dashboards, analytics views, and inventory screens need to render data tables that combine sorting, filtering, column manipulation, row selection, and pagination over datasets ranging from a few hundred rows to millions. Teams routinely build this from scratch, then hit three failure modes: client-side sorting applied on top of server-side pagination (which silently sorts only the visible page), DOM explosion when hundreds of cells re-render per sort click, and filter state that dies on refresh because it lives only in component state. A data table is a state machine over a dataset, and the architecture decisions — where each operation runs, where state lives, and what the DOM actually renders — determine whether the table feels instant or janky.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Architecture: Where Operations Run

1. **Client-side below the ten-thousand-row threshold.** TanStack Table's own guidance is that headless client-side processing (sorting, filtering, grouping, pagination) performs decently up to tens of thousands of rows held in memory. Below that threshold, prefer client-side operations: they give instant feedback, work offline, and remove server round-trips from every sort click. Community consensus (Reddit r/reactjs threads on TanStack usage) is that if all rows fit comfortably in memory, client-side mode is the simplest and best UX.

2. **Server-side with manual flags above it.** For large or expensive datasets, set manualPagination, manualSorting, and manualFiltering to true. The table then treats your server responses as the source of truth and only manages UI state (which column is sorted, which filters are active) while the API does the heavy lifting. The critical rule from the TanStack sorting guide: be consistent — never mix client-side sorting with server-side pagination, because the client can only sort rows it has loaded, which is exactly the visible page.

3. **Use a headless table library even in manual mode.** A common mistake is dropping TanStack Table entirely when going server-side. The headless library still provides column state management, sorting indicators, filter wiring, column pinning, resizing, and selection semantics that you would otherwise rebuild badly. You keep the state machine and swap the data source.

4. **Pair server-side mode with a query cache.** Integrate TanStack Query (or SWR) so that a sort-filter-page combination maps to a cache key. Returning to a previously viewed combination is instant, background refetch keeps data fresh, and optimistic placeholders avoid layout pop when pages change.

5. **Decide the crossover with measurement, not folklore.** The real limits depend on cell complexity (a row of text cells is cheap; a row with three interactive components is not) and on target devices. Prototype with production-shaped data on a mid-range phone before committing to client-side processing.

## State: Sorting, Filtering, and the URL

1. **Sync table state to URL search params.** Sort direction, active filters, page number, and page size belong in the URL (e.g., ?sort=-created_at&status=active&page=3). This makes views shareable, keeps back-button behavior sane, survives refresh, and gives support engineers an exact reproduction of what the user saw. A GitHub discussion on TanStack Table (#3945) repeatedly requests this as an official example because it is the single most common production pattern.

2. **Treat filter state as typed, serializable data.** Define filters as a discriminated union (text-contains, select-equals, date-range, number-between) rather than ad-hoc strings. Typed filters serialize cleanly to URL params, validate on parse, and make server-side query builders mechanical instead of guesswork.

3. **Debounce text input, not toggles.** Free-text filters should debounce (200-300 ms) before triggering a fetch; discrete controls (dropdowns, checkboxes) should fire immediately. Combine with TanStack Query's built-in deduplication so rapid changes cancel stale requests rather than racing them.

4. **Keep derived state out of the store.** Store only the canonical filter/sort/page inputs; derive visible rows, counts, and "no results because of filters" messages from them. Two sources of truth for the same concept guarantees drift bugs.

## Virtualizing the Grid

1. **Virtualize rows, not the whole table.** Row virtualization (via TanStack Virtual or similar) renders only the rows intersecting the scroll viewport plus overscan, positioned absolutely inside a spacer row that reserves total height. This keeps the DOM in the low hundreds of elements regardless of row count. Apply it on top of a real table element (or an ARIA grid role) so screen readers still perceive tabular structure.

2. **Virtualize columns for wide tables.** Financial and audit tables with 50+ columns blow up horizontally as well. Column virtualization works the same way along the X axis and is what makes frozen/ pinned columns perform: render the pinned region outside the virtualized window so it never unmounts during horizontal scroll.

3. **Measure dynamic row heights honestly.** estimateSize gets you started, but rows with wrapping text need measured dynamic sizing with a resize observer or the virtualizer's measureElement. Budget for re-measurement churn: stabilize row content (fixed line clamps) where possible so heights settle after the first pass instead of oscillating.

4. **Reuse the virtual list lessons.** The same overscan, key-stability, and scroll-element rules documented in the react-virtual-list article apply; a data table is that problem plus sticky headers, column alignment, and selection state. Read that article before re-deriving the mechanics.

## Selection and Bulk Operations

1. **Track selection across pages when server-side.** Store selected row IDs (or a filter expression for select-all) rather than indexes, because page changes invalidate indexes. For select-all, store the intent ("all matching current filters") and resolve IDs server-side at action time; the row count shown in the bulk bar should come from the server.

2. **Render the bulk action bar as a derived layer.** A bar showing "12 selected — Archive / Export / Clear" should be a pure function of selection state, positioned so it does not shift table layout (a floating bar or sticky footer avoids CLS when selection changes).

3. **Make selection keyboard and screen reader accessible.** Use checkbox cells with real labels, support shift-click range selection, and announce selection counts via a polite live region. Row-only click-to-select is hostile to both keyboard users and people doing accidental clicks.

## Performance and Pitfalls

1. **Memoize column defs and cell renderers.** Column definitions recreated every render invalidate the table's internal memoization; cell renderer components recreated inline defeat React's reconciliation. Define columns with stable references (useMemo keyed on real dependencies) and keep heavy cells as named components.

2. **Avoid re-rendering the table on every keystroke.** When a text filter lives inside the table toolbar, route its transient state through a ref or local input state and only commit to table state on debounce; otherwise every keystroke re-renders every visible row.

3. **Test with the worst case, not the happy path.** Fuzz the table with maximum columns, maximum rows, longest cell content, and rapid sort-filter-page interactions. Watch for the classic bug where sorting while a fetch is in flight applies the old sort to the new data — abort or version in-flight requests so responses match the state that requested them.
