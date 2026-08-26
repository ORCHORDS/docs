# esm-cjs-load-performance

**Issue:** Node.js application and CLI startup time is dominated by module resolution and evaluation, and the choice between CommonJS (require) and ES modules (import) has real, measurable performance consequences that go beyond style preference. The two systems have different caching models: require keeps a synchronous, programmatically accessible cache (require.cache) with very cheap repeat lookups, while ESM's async resolution pipeline and module map historically made re-importing the same ES module roughly 15-25x slower than re-requiring an equivalent CJS module (Node issue #<number>). At the same time, ESM's static structure enables tree-shaking and better bundling. This article covers where the startup costs actually come from, the interop tax, and how to get module-load time under control in a codebase that inevitably contains both formats.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Where startup cost comes from

1. **Resolution walks the filesystem.** Every require or import of a bare specifier probes node_modules directories up the tree with real stat calls; deep dependency graphs cause thousands of syscalls before a single line of app code runs. Tools like --cpu-prof or node --cpu-prof then show the telltale resolution hot spots.
2. **CJS is synchronous and cached by reference.** require resolves, loads, wraps, and evaluates once, then caches the exports object; repeat requires are a dictionary hit. This is why large CJS codebases can still boot fast despite no static analysis.
3. **ESM is asynchronous by design.** ESM resolution and instantiation go through a promise-based pipeline with no user-accessible cache; repeated dynamic import() of the same specifier must await the module map lookup, which measured 15-25x slower than the CJS equivalent before targeted optimizations landed in recent Node versions — still a reason to avoid import() in hot loops.
4. **Top-level execution dominates either way.** Module-system overhead is per-module metadata work; side effects at module scope (config parsing, client construction, filesystem reads) are usually the bigger bill. Measure before blaming the format — the Performance inspector or a simple perf_hooks timeline separates the two.

## Caching model differences

1. **No require.cache equivalent in ESM.** CJS code can invalidate, inspect, or mutate the module cache (at its own peril); ESM exposes nothing, so cache-busting or hot-reload strategies must use file URLs plus query strings or a module registry, each with re-resolution costs.
2. **Loader hooks add latency.** Both systems support customization (require extensions unofficially, ESM loader hooks officially), but every ESM customization hook is an async hop per module; bundling away the need for hooks is usually faster than clever loaders.
3. **Bundlers erase the difference.** When a bundler (esbuild, tsup, Rolldown) inlines the dependency graph into one file, resolution and cache semantics vanish and the CJS/ESM gap collapses to near zero — the pragmatic answer for CLIs where startup is the product.

## The interop tax

1. **Transpilation layers are the hidden cost.** ts-node, tsx, and Babel registers hook resolution to compile TypeScript at load time; on large graphs this multiplies startup several-fold. Ship compiled JavaScript (or use the increasingly capable native TypeScript stripping) for production paths, keeping transpilers in dev only.
2. **require(esm) is possible but constrained.** Modern Node lets CJS require synchronous ES modules — but not modules using top-level await, and each require call still pays ESM pipeline costs; mixing formats per-call in hot paths is the worst of both worlds.
3. **Dual-format packages resolve twice.** Packages shipping both formats via exports conditions add conditional resolution on every import; standardizing the internal codebase on one format (ESM for new code, per the ecosystem direction) keeps the graph uniform and predictable.
4. **Named-export interop shapes.** Consuming CJS from ESM triggers cjs-module-lexer analysis to surface named exports; default-vs-named mistakes cause subtle runtime deoptimizations and bugs that are cheap to avoid with consistent import discipline.

## Mitigation strategies

1. **Lazy-import the heavy tail.** Move optional or rarely used dependencies (report generators, SDKs for features behind flags) behind dynamic import() at first use; startup then pays for them only when the user invokes the feature. This is the single highest-leverage fix for CLI startup.
2. **Prefer many small awaits over eager module-scope work.** Constructor-at-module-scope (creating DB clients, reading env-dependent files) forces worst-case loads even in tests; move to explicit init functions so import stays cheap by construction.
3. **Snapshot and measure startup in CI.** Time a --version or no-op invocation in CI (and with node --cpu-prof in a script) and fail on regressions beyond a percentage; startup time degrades a few milliseconds per dependency and nobody notices without a gate.
4. **Prune the graph.** module-deps or npx dependency-tree dumps reveal accidental heavyweights (moment pulled in transitively, a CLI framework imported for one helper); every removal cuts resolution, IO, and parse time across every invocation.
5. **Use V8 compile cache and snapshots where applicable.** node --snapshot-blob and module.enableCompileCache() (in recent Node releases) persist parse results across runs, cutting cold-start parse cost for both formats — cheap wins for frequently run CLIs.

## Decision guidance

1. **New packages: ESM-only.** The ecosystem direction is ESM; static analysis, tree-shaking, and top-level await outweigh the (shrinking) resolution overhead, and bundling removes it where it matters.
2. **Hot loops: cache the promise.** If code must dynamic-import repeatedly, memoize the import() promise yourself — a local Map from specifier to promise sidesteps repeated pipeline costs and is faster than re-awaiting the module map on older Node versions.
3. **Serverless and Workers: bundle.** Cold-start environments multiply module-load costs; bundling to a single file (plus compile cache where the runtime allows) is standard practice for exactly this reason.
4. **Do not rewrite working CJS for speed alone.** A mechanical CJS-to-ESM migration rarely improves runtime performance by itself and risks subtle behavior changes; migrate for ecosystem and tooling reasons, and recover startup time first through lazy loading, pruning, and caching.
