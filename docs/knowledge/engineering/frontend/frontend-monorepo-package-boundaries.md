# frontend-monorepo-package-boundaries

**Issue:** A frontend monorepo starts as a productivity win — shared code, one lockfile, atomic cross-app changes — and decays into a big ball of mud when nothing enforces which package may import which. Feature packages reach into app internals, UI components import server code, everything silently depends on half the repo through phantom dependencies, and a change anywhere invalidates the whole CI cache. The 2025-2026 toolchain (pnpm workspaces with the catalog: protocol, Turborepo or Nx for task orchestration, ESLint boundary rules and dependency-cruiser for import policing) makes boundaries cheap to enforce automatically. The engineering problem is deciding the layering model, encoding it in tooling, and keeping task graphs and caching aligned with it — so "small, focused packages" is a property the CI proves, not a hope.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Workspace structure and layering

1. **Directory-per-role.** The conventional layout is apps/ for deployables (web, docs, mobile shell), packages/ for publishable libraries, and optionally tooling/ or configs/ for shared config presets. Turborepo's guides structure repos exactly this way and its examples assume the apps/packages split.
2. **Layers flow one way.** Define an allowed direction — apps may import features, features may import shared UI and utilities, shared packages may not import upward. Encode the layers once and reference them from every enforcement tool so rules do not diverge.
3. **Small, focused packages over mega-packages.** ui, api-client, auth, design-tokens, utils each stay individually graspable; a single shared package becomes a coupling magnet where every app transitively depends on every other app's needs.
4. **Internal packages need no build step.** Turborepo's "internal packages" pattern lets apps consume workspace packages as source (via exports pointing at TS files) so the app bundler compiles them — removing a whole class of build-order and stale-dist bugs for packages that never publish.
5. **One package.json per boundary, not per folder habit.** Creating a package has a cost (config, CI, review surface); promote folders to packages when multiple consumers or team ownership justify it.

## Dependency hygiene

1. **workspace:* for internal deps.** Always reference workspace packages with the workspace protocol so pnpm links the local source and versions can never drift between published and in-repo copies.
2. **catalog: for third-party versions.** pnpm catalogs (defined in pnpm-workspace.yaml) let every package.json declare "react": "catalog:" and expand centrally to one version — upgrades touch a single line, duplicated runtime versions (which cause real bugs) become impossible, and merge conflicts vanish. Use named catalogs (catalog:react18) only during intentional version migrations. Recent pnpm versions add catalogMode strict to forbid non-catalog versions and cleanupUnusedCatalogs to prune stale entries.
3. **Kill phantom dependencies.** npm/yarn hoisting lets code import packages it never declared. pnpm's isolated node_modules layout already blocks this — treat any "works from node_modules but not in package.json" import as a defect and declare it explicitly.
4. **Explicit exports in each package.** Use the package.json exports field to publish only the intended entry points of internal packages; deep imports into package internals are the fastest way to create undeletable code. TypeScript's moduleResolution bundler honors exports, so the type system enforces it too.
5. **Audit duplication on schedule.** Run pnpm why (or an equivalents report) in CI weekly to catch accidental second versions of react, date libraries, or lodash creeping in through transitive deps.

## Enforcing boundaries in CI

1. **eslint-plugin-boundaries.** Declare element types (app, feature, ui, util) by path glob and an allowed-import matrix; the plugin fails lint on any illegal import direction or undeclared dependency, with autosuggest messages that tell the author the legal alternative.
2. **dependency-cruiser.** Complement lint with rule graphs: reachability rules (no package may reach into apps/), orphan detection (unreferenced packages to delete), and cyclic-dependency checks — plus generated dependency graphs that make the architecture reviewable as a picture, not intuition.
3. **import/no-extraneous-dependities for the long tail.** Even with boundaries enforced, keep a base ESLint rule ensuring every import maps to a dependency declared in that package's own package.json — the cheapest possible phantom-dependency alarm.
4. **Type-level boundaries with project references.** If using tsc project references, the reference graph is itself a boundary: a package simply cannot typecheck against something it does not reference. Some teams treat this as the primary enforcement and lint as the human-friendly error layer.
5. **CODEOWNERS per package.** Route PRs touching a package to its owning team; boundaries are an organizational contract as much as a technical one, and review is where violations get negotiated.

## Task orchestration and caching

1. **Turbo pipelines encode the build graph.** Declare tasks (build, lint, test, typecheck) in turbo.json with dependsOn: ["^build"] so a package's dependencies build first, and declare outputs for caching (dist/, .next/, coverage/). Turborepo only rebuilds what changed via its hash of inputs, environment variables, and dependency outputs.
2. **Filter for scoped work.** Use turbo run test --filter=web... (package and its dependents) for local iteration and --filter=[origin/main] in CI to run only affected tasks — the difference between 4-minute and 40-minute PR checks.
3. **Remote caching for CI speed.** Share the turbo cache across CI runners and developers so identical inputs never rebuild; this is the single biggest monorepo CI win and is safe because cache keys are content hashes.
4. **Keep tasks pure and hermetic.** Caching silently breaks when tasks read undeclared inputs (env vars not in env, files outside inputs) or write outside outputs. Treat a cache-miss-that-should-hit as a bug in task config, not bad luck.
5. **One task runner, uniform scripts.** Standardize script names across packages (build, dev, lint, test) so turbo tasks and developer muscle memory work everywhere; per-package clever names break --filter workflows.

## Anti-patterns and failure modes

1. **The shared-everything package.** A packages/shared that every app imports becomes the coupling point where any change risks everything; split by domain and let the boundary rules prove independence.
2. **Cross-app deep imports.** Importing apps/web/src/lib/foo from the mobile app couples deployables together and defeats scoped CI. Extract the code into a package first, then import the package.
3. **Version drift through published packages.** If an internal package is published to a registry and apps pin old versions, the monorepo benefit is gone — consume workspace packages directly, or enforce lockstep releases with changesets.
4. **Boundary rules that lag reality.** Rules that only exist in a wiki rot in weeks; if an import direction is legal in the architecture, it must be legal in eslint-plugin-boundaries config in the same PR that establishes it.
5. **Monorepo as an end in itself.** If a repo has one app and three small packages, workspaces plus catalogs are enough; full Turborepo/Nx machinery pays off with multiple apps and teams — adopting it early is fine, but do not let tool setup consume the actual product work.
