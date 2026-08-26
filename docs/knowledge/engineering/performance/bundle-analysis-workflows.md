# bundle-analysis-workflows

**Issue:** The team has a byte budget for bundles, but nobody knows what is inside them or which PR grew what. Analysis happens as a panic ritual when a Lighthouse score drops: someone runs webpack-bundle-analyzer locally, squints at treemaps of a build that may not match production config, and guesses. This article defines a repeatable bundle analysis workflow: accurate tools, per-PR diffs, budget gates in CI, and a triage loop that attributes bytes to owners.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Tool Selection

1. **source-map-explorer for accuracy.** It derives module sizes from the actual source maps of the built artifacts rather than bundler-internal parsed-size heuristics, which is why the Angular team explicitly recommends it over webpack-bundle-analyzer when you need trustworthy numbers. Run it against exactly the files you ship (`source-map-explorer 'dist/assets/*.js'`), including per-module output for CSV-based tracking.
2. **webpack-bundle-analyzer / rollup-plugin-visualizer for exploration.** The treemap is unmatched for human discovery ("why is moment with all locales in here"), but treat its sizes as approximate; use it to find structure, then confirm with source-map-explorer.
3. **Statoscope for CI and diffing.** Produces a webpack/Rollup report from stats or source maps, validates configurable budgets (`statoscope validate`), and diffs two builds (`statoscope diff old.json new.json`) naming which modules grew — this is the piece that turns analysis into a regression gate rather than a retrospective.
4. **size-limit for lightweight budgets.** GitHub-native CI action that fails a PR when a configured entry point's gzip size crosses a threshold, with a comment showing the delta; ideal for libraries and simple apps where full statoscope reports are overkill.
5. **Vendor-provided dashboards.** Next.js `@next/bundle-analyzer`, Vite `rollup-plugin-visualizer`, esbuild `--metafile` + esbuild-visualizer — same rules apply: exploration locally, source-map-accurate numbers for gates.

## The Workflow

1. **Generate analysis from production builds only.** Run the analyzer against the exact artifacts produced by the release build (same minimizer, same NODE_ENV, source maps enabled but not deployed). Dev builds and different chunk settings make the analysis fiction.
2. **Commit a baseline, diff every PR.** Store the build report (stats JSON or source-map-explorer CSV) on the default branch; each PR generates its own and the CI job posts a byte delta per chunk — "utils.js +42KB: moment added by #4812" is reviewable, a global "bundles got bigger" is not.
3. **Gate with tiers, not one number.** Hard-fail when a PR adds more than N KB gzipped (for example 10KB) to any entry chunk; warn on smaller growth; auto-fail any PR that adds a new dependency over a size threshold without an inline justification. Budgets per route matter more than one global budget in code-split apps.
4. **Attribute bytes to owners.** Tag modules by team or package in the report (path prefixes usually suffice) so the delta comment names an owner, not just a file; shared-vendor chunks get a shared owner.
5. **Triage loop on regressions.** When a gate fires: open the diff report, find grown modules, decide — move to dynamic import, replace with a lighter dependency, tree-shake a named import, or accept with justification. Re-run the gate. Never merge "temporarily" with a follow-up ticket and no date.

## Reading the Numbers Correctly

1. **Parsed vs gzip vs rendered sizes.** Track gzip for network budgets, parsed size for parse/compile main-thread cost (large parsed JS delays INP even on fast networks), and render size where tooling supports it. Budget conversations that don't name which size are meaningless.
2. **Modules multiply across chunks.** A package duplicated into several route chunks costs more than its single size; check duplication (source-map-explorer shows the same module in multiple files) before celebrating a small per-chunk number.
3. **Polyfills and helpers hide the tail.** core-js, regenerator-runtime, tslib helpers, and per-package dedup misses commonly account for 10-20% of app bundles; analyze with deduplication info visible.
4. **Lazy chunks count toward the budget.** Teams gate only the initial bundle and let lazy chunks balloon; total transferred per route is the user-visible metric, so track entry + route chunks separately.

## Gotchas

1. **Sourcemap accuracy depends on the toolchain.** Minifiers that mangle aggressively can smear attribution across adjacent modules; keep sourcemap generation in release builds and spot-check suspicious "unknown" buckets.
2. **Tree-shaking illusions.** The analyzer shows what shipped, not why; an import of one function from a barrel file can drag the whole library — verify with the report after switching to deep imports rather than assuming.
3. **Budget gates rot without re-baselining.** When a deliberate large feature lands, re-baseline deliberately with a written threshold change; otherwise teams route around the gate (chunk splitting to dodge per-entry limits) instead of respecting it.
4. **Local treemaps of stale builds mislead.** Always regenerate before analyzing; the single most common analysis error is reading last week's artifacts.

## Related

bundle-size-budgets, javascript-bundle-size, tree-shaking-optimization, code-splitting-strategies, dynamic-import-patterns
