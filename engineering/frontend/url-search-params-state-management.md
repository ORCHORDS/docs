# url-search-params-state-management

**Issue:** Filter panels, table pagination, tab selection, and modal state keep getting duplicated between component state and the URL, so refreshing loses the view, sharing a link does not reproduce it, and the browser back button behaves randomly. Teams reach for a global store (Redux/Zustand) for state that is already global, serializable, and shareable by nature: the query string. The problem is that hand-rolled `window.location.search` parsing with `URLSearchParams` is brittle — no type safety, no defaults handling, no shallow-routing awareness, and every read/write re-renders more than it should.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What belongs in the URL

1. **Anything a user could reasonably bookmark or share.** Search filters, sort order, page number, tab selection, and detail-panel-open flags belong in the query string because they define "which view of the data am I looking at", not "who am I". The TanStack team's framing is right: search params are global, serializable, shareable state for free.
2. **Anything that should survive a refresh.** If losing the state on F5 would confuse the user, it is URL state. Local component state should only hold truly ephemeral things like hover position or uncontrolled input drafts.
3. **Anything the back button should navigate through.** Closing a filter drawer or a detail overlay via back is expected mobile behavior; encoding it as `?detail=123` gives you that without a history stack hack per interaction.
4. **What does NOT belong: secrets and heavy structure.** URLs land in browser history, server access logs, analytics pipelines, and referrer headers — never put tokens, emails, or IDs a user would not share. Deeply nested objects encoded as JSON query params are a smell; flatten to scalar keys.
5. **The serialization test.** A good heuristic: if you cannot write a stable string-to-value parser (with defaults) for the state, it is too complex for the URL and belongs in a store or the server.

## The core pattern (type-safe adapter hooks)

1. **Wrap search params in typed hooks, never read them raw.** A `useQueryState(key, parser)` hook (the nuqs API, or a hand-rolled `useSearchParams` wrapper in React Router/TanStack Router) returns `[value, setValue]` like `useState` but persists to the URL. Each key declares its type (`parseAsString`, `parseAsInteger`, `parseAsIsoDate`, or a `parseAsEnum`).
2. **Always declare defaults.** Without a default, unset keys surface as `null` and every consumer does a null dance. With `defaultValue`, the hook returns the default when the key is absent, and writers omit the key when the value equals the default — keeping URLs clean (`?page=1` should never appear).
3. **Batch updates with a functional multi-key setter.** Changing `query`, `sort`, and `page` in three separate navigations pushes three history entries and triggers three renders. Use the library's `useSetQueryStates` (nuqs) or build one navigation call per user action so one click equals one history entry.
4. **Use shallow routing where available.** In Next.js App Router, `nuqs` adapters update the search params without re-rendering server components or re-fetching the layout; hand-rolled `router.replace` does not guarantee this. In TanStack Router, schema-validated search params are a first-class feature — prefer its built-in validation over bolted-on zod parsing.
5. **Validate at the parse boundary, not at render time.** Treat the URL as untrusted input (users hand-edit it). Parsers should clamp integers (`page` to `>= 1`), reject enum misses by falling back to the default, and strip empty strings — a malformed URL should degrade to the default view, not crash the page.

## Common bugs

1. **Infinite render loops from reading params in an effect and writing them back.** Deriving state from the URL during render (or via a memo keyed on the serialized params) instead of syncing in `useEffect` avoids the classic "setState from props in effect" ping-pong. The URL is the source of truth — derive, do not synchronize.
2. **Stale params in event handlers.** Closures over `searchParams` inside `useEffect`-registered listeners capture the old URL. Read from the ref/current location at call time, or include the params in the dependency array deliberately.
3. **Server/client hydration mismatches.** If the server renders with different params than the client URL (e.g., behind a proxy that strips them), guard with `Suspense` around `useSearchParams` consumers in Next.js and avoid deriving initial markup from params that arrive only after hydration.
4. **Key collisions and version drift.** Renaming `q` to `query` orphans every previously shared link. Keep a small alias map (old key -> new key) at the parser layer, and treat key renames as a migration, not a refactor.
5. **Back-button surprises from replace-vs-push confusion.** Use `history.push` for genuine navigation (applying filters) and `history.replace` for state that should not add entries (typing-as-you-search debounce, autosave indicators). Mixing them up is why users press back and land three filter-changes ago.
6. **Unbounded cardinality keys.** Keys like `?ids=1,2,3,...` with thousands of values hit URL length limits (~2k safe in old proxies, larger in modern browsers but not in logs). Cap, paginate, or move to server-side saved filters with a short token in the URL.

## Testing and observability

1. **Snapshot the serialized URL after each interaction in tests.** Testing-library assertions on `window.location.search` after clicking "Apply filters" catch regressions that component-state tests miss, because the URL is the contract with the user.
2. **Test parser edge cases as units.** Empty string, missing key, `NaN`, negative page, duplicated keys (`?page=2&page=3` — `URLSearchParams.get` returns the first), and unicode values are a 20-line table-driven test that eliminates an entire bug class.
3. **Instrument real-world param combos.** Analytics on the distribution of query keys reveals which filters users actually share, and flags accidental PII leakage into URLs before an audit does.
4. **Related reading in this knowledge base:** `react-router-v7-patterns.md` (search param validation), `next-js-app-router-patterns.md` (`searchParams` prop vs `useSearchParams`), and `state-management-patterns.md` for the server-state versus URL-state boundary.
