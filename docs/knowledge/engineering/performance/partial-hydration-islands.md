# partial-hydration-islands

**Issue:** Server-side rendering solves first paint but creates a second performance problem: hydration. The full React/Vue/Svelte runtime plus the component tree must download, parse, and execute on the client before the server-rendered HTML becomes interactive, and on content-heavy pages that JavaScript cost is paid for thousands of components that have no interactivity at all. Islands architecture (popularized by Astro) and resumability (Qwik) attack this by shipping JavaScript only for the interactive regions — islands — embedded in otherwise static HTML. With 2025-era frameworks, content sites routinely ship 10-50 KB of JS instead of 150-400 KB, which directly improves INP, TBT, and Time to Interactive while keeping SEO-friendly server-rendered markup.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why full hydration is expensive

1. **Hydration is a full re-render in disguise.** The client framework re-executes every component function to rebuild its virtual tree and reconcile it with server HTML, then attaches listeners. A page with 3,000 components pays for 3,000 executions even if only 30 of them ever respond to input.

2. **The framework runtime is a fixed floor.** Before any component hydrates, the browser must download, parse, and compile the renderer itself — roughly 40-140 KB compressed for mainstream frameworks. Content sites with one carousel and a search box pay this tax for almost no benefit.

3. **Everything blocks the first interaction.** Because hydration is typically all-or-nothing per page (or per route segment), a single slow chunk delays interactivity everywhere. Long Tasks during hydration are a leading cause of poor INP on SSR news and e-commerce pages.

4. **Waterfalls compound the cost.** Hydration often starts only after the main bundle downloads; interactive islands that then fetch their own data add a client-side request waterfall on top. The visible page looks fast while interaction latency stays high.

## Islands architecture mechanics

1. **Static shell, interactive pockets.** The framework (Astro is the canonical 2025 example) renders the whole page to HTML at build or request time, then hydrates only the components explicitly marked as islands. The rest of the page is plain HTML with zero client JavaScript.

2. **Hydration triggers control the timing.** Islands can hydrate on load, when idle (requestIdleCallback), when visible (IntersectionObserver), or only on first interaction. Choosing client:visible or client:idle for below-the-fold widgets moves their JavaScript cost off the critical path entirely.

3. **Each island carries only its own dependency graph.** Tree-shaking operates at island granularity: a page with a vanilla-JS menu, a React chart, and a Svelte form ships three small islands rather than one merged bundle, and unused framework code never downloads.

4. **Server components complement islands.** Data-heavy regions can render on the server (or via server components in the host framework) so that only event handlers and stateful leaf widgets become islands, keeping both HTML completeness and client JS minimality.

## Resumability versus hydration

1. **Qwik serializes instead of re-executing.** Instead of re-running components on the client, Qwik emits the application state and lazily-loadable event-handler references directly into the HTML, so the browser "resumes" exactly where the server stopped. There is no hydration phase and no framework runtime download until an interaction requires one.

2. **Handler-level code splitting is automatic.** Because listeners are serialized as references, the code for a click handler downloads only if that handler actually fires. This inverts the default: JavaScript becomes interaction-triggered rather than interaction-enabling.

3. **Trade-off: serialization weight and tooling complexity.** Resumability moves cost into the HTML payload (state and references inline in the document) and requires a compiler with strict constraints on how state is captured. For small, highly interactive apps the HTML overhead can offset the JS savings.

4. **The choice is content-shaped.** The more a page is content with pockets of interactivity, the more islands/resumability wins; the more it is a continuously interactive application (dashboards, editors), the more the techniques converge back toward a single hydrated root, and gains shrink.

## Costs, edge cases, and anti-patterns

1. **Islands are state boundaries.** Moving state between islands requires explicit stores or signals; accidentally sharing a framework store across many islands re-couples their loading and recreates monolithic hydration cost.

2. **Server render time is still your problem.** Islands reduce client cost, not build/request-time cost. A slow build-time page generator (Astro) or slow SSR still delays TTFB and LCP; the techniques are complementary, not substitutes.

3. **Third-party widgets sabotage islands.** One embed that ships 300 KB of monolithic JS inside an island erases the budget discipline. Wrap heavy third-party embeds in facades that load code on interaction.

4. **Watch idle-hydration interaction latency.** client:idle and on-interaction islands add a small delay before first input works. Measure INP from the field; if an interaction-triggered island causes slow first responses on mobile, promote it to visible or load.

## Adoption and measurement

1. **Migrate the worst pages first.** Pick routes with the highest traffic and lowest interactivity ratios — marketing, docs, content listings. These see the largest JS reduction for the least architectural risk.

2. **Track shipped JS per route, not per bundle.** Instrument the framework's build output (or use bundle analyzers) to report JS transferred per route after migration; the goal metric is KB of JS on the wire for a cold visit.

3. **Validate Core Web Vitals in the field.** Islands primarily improve INP and TBT via smaller hydration Long Tasks. Confirm with RUM attribution that hydration Long Tasks disappear on migrated routes and that LCP did not regress from a slower static shell.

4. **Re-run accessibility and functional checks post-migration.** Zero-JS HTML regions behave differently from hydrated ones (progressive enhancement is a feature, but forms and menus must still work or enhance). Automated a11y suites plus keyboard-only passes catch regressions the perf dashboard will not.
