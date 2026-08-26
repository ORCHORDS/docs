# hydration-mismatch-debugging

**Issue:** After shipping server-side rendering (React/Next.js, Remix, or RSC payloads), the console floods with errors like "Text content does not match server-rendered HTML" or "Hydration failed because the server rendered HTML didn't match the client." The page usually still renders, so teams learn to ignore the warning — but a hydration failure means React throws away the entire server DOM and re-renders the tree client-side, destroying the performance benefit of SSR and causing visible flicker, lost focus, and re-run effects. The root causes are almost always one of a small set: nondeterministic render output, browser-only values read during render, invalid HTML nesting, or browser extensions mutating the DOM before React attaches.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Root causes (ranked by frequency)

1. **Time-dependent output.** `Date.now()`, `new Date().toISOString()`, `Date.toLocaleTimeString()`, or `setTimeout`-derived values rendered during SSR differ from the client render milliseconds later. Any timestamp formatted without a fixed reference point is a guaranteed mismatch whenever server and client clocks or tick boundaries disagree.
2. **Random values.** `Math.random()`, `crypto.randomUUID()`, shuffled arrays, or generated IDs (except `useId`, which is deterministic across server/client). Classic offenders: key-generation helpers, avatar color pickers, and test-data seeders left in components.
3. **Browser-only APIs during render.** Reading `window.location.hash`, `localStorage`, `navigator.userAgent`, `document.cookie`, or `window.innerWidth` in the component body. The server has no such objects (or different ones), so first client render disagrees with server HTML. This includes feature detection like `matchMedia` done inline.
4. **Browser extensions mutating the DOM.** Grammarly injects `data-new-gr-c-s-*` attributes on `<body>`, password managers wrap inputs, React DevTools marks nodes, dark-mode extensions add inline styles — all before hydration attaches. This is why a mismatch appears only for some users and never in incognito. Remix issue #<number> and multiple Next.js threads confirm React Dev Tools itself can trigger it.
5. **Locale/timezone divergence.** Formatting dates, numbers, or currency with `Intl` while the server runs UTC/en-US and the client runs the user's locale. `new Date().toLocaleDateString()` is locale- and timezone-sensitive; server (UTC) vs client (UTC+9) produce different strings for the same instant.
6. **Invalid HTML nesting.** `<div>` inside `<p>`, `<a>` inside `<a>`, `<button>` inside `<button>`, or `<tbody>` handled incorrectly. The browser's HTML parser silently relocates or drops the invalid nodes when parsing server HTML, so React's expected tree no longer matches the actual DOM. These fail 100% deterministically.
7. **Mismatched render conditions from external mutable state.** Reading a global store, `document`-cached value, or module-level singleton during render that was initialized differently on the client. The correct primitive is `useSyncExternalStore` with a `getServerSnapshot`, not direct reads.

## Systematic fixes (in order of preference)

1. **Two-pass rendering with `useEffect`.** Render a stable placeholder (skeleton, empty string, fixed server-safe value) on the first pass, then swap in the browser-only value inside `useEffect` after hydration completes. This is the default fix for clocks, `window` dimensions, and localStorage reads; the tradeoff is one extra render and a possible flash of placeholder.
   ```tsx
   const [time, setTime] = useState<string | null>(null); // null on server AND first client render
   useEffect(() => setTime(new Date().toLocaleTimeString()), []);
   ```
2. **`useSyncExternalStore` for external mutable state.** For URL hash, media queries, or third-party stores, pass a `getServerSnapshot` that returns the server-known value so hydration uses the same snapshot, then the subscription updates it post-hydration without a mismatch.
3. **Deterministic IDs via `useId`.** Replace `Math.random()`-based or incrementing-global IDs with React's `useId` (stable across server and client). Seed any shuffle with a deterministic PRNG keyed on props if order must vary but SSR must match.
4. **Stabilize locale/timezone at the data layer.** Format dates and numbers on the server with an explicitly pinned locale/timezone, or render ISO strings and localize after mount. Never let implicit host locale decide SSR output.
5. **Fix nesting, don't paper over it.** Replace `<p><div>…</div></p>` with `<p><span className="block">…</span></p>`, unwrap nested anchors, and check the HTML validator — these mismatches indicate real rendering bugs that also affect SEO parsers and screen readers.
6. **`next/dynamic` with `ssr: false` for genuinely client-only islands.** Widgets that cannot render on the server (maps, editors, browser-API-dependent visualizations) should be dynamically imported with SSR disabled so they never participate in hydration comparison.

## Debugging workflow

1. **Read the React 19 diff first.** React 19 rewrote hydration errors to print the actual server/client diff and the component stack — in React 18 you only got "didn't match" plus a stack trace pointing at the wrong sibling. Upgrade (or at least read the React 19 error output format in docs) before binary-searching blind.
2. **Reproduce in incognito with extensions off.** If the error vanishes in incognito, an extension is the culprit — the fix is `suppressHydrationWarning` on that element or ignoring it, not refactoring your app. Check the diff for extension fingerprints (`data-gr-*`, `grammarly-*`, `cw-*`).
3. **Bisect the tree.** Comment out halves of the page (or use `dynamic(ssr:false)` to neutralize subtrees) until the error disappears; the mismatching node is in the last subtree standing. The error's component stack in React 19 usually shortens this to one or two cuts.
4. **Diff the served HTML against client HTML directly.** `curl` the SSR output and save it, then in the browser before hydration completes, compare with the same nodes — mismatched attribute/text pairs jump out. This is the definitive test for extension interference vs. app bugs.
5. **Run the deterministic checks.** Grep the codebase for `Date.now`, `Math.random`, `toLocale`, `window.`, `localStorage` in components that render on the server; each hit inside render is a candidate. CI-greppable and catches most cases before they ship.

## `suppressHydrationWarning` — last resort only

1. **What it actually does.** It suppresses warnings for text and attribute differences on exactly that element (commonly `<body>` or a time element) — it does not suppress mismatches in child elements, and it does not fix anything. React still proceeds as if the element matched where it can.
2. **Legitimate uses.** Extension-corrupted attributes on `<html>`/`<body>` (including dark-mode class injection), timestamps that intentionally differ, and `next-themes`-style theme classes — the two known-good cases in the Next.js docs.
3. **Why it's dangerous as a habit.** Every suppressed warning could be hiding a real mismatch — invalid nesting, lost server HTML, a broken RSC payload — and once the tree falls back to client render, you've silently paid the full SSR cost for nothing. Scope it to one element with a comment naming the cause, and never apply it to a container "to make errors go away."
4. **Check `reactStrictMode` and double-invocation myths.** Strict Mode double-invokes render in dev, which surfaces existing nondeterminism (a `Math.random()` now visibly produces two different values) but does not itself cause hydration mismatches. If a mismatch appears only in dev with Strict Mode, you have real nondeterminism, not a Strict Mode bug.

## Related

- `react-suspense-boundaries.md`
- `next-js-app-router-patterns.md`
- `react-hooks-rules.md`
- `css-in-js-tradeoffs.md` (SSR hydration cost of runtime CSS-in-JS)
