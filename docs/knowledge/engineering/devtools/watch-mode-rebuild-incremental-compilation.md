# Watch Mode and Incremental Compilation Orchestration

Modern build stacks rebuild only what changed: TypeScript's `--build --watch`, esbuild's incremental transforms, Rust's incremental compilation, Vite's module-graph invalidation. Watch mode is the developer-facing loop (save → rebuild → hot reload in hundreds of milliseconds); incremental compilation is the machinery underneath (dependency graphs, caches, change classification). The two compose into a fast inner loop — or into a reliability hazard: stale caches serving wrong output, watchers missing edits on network filesystems, and memory creep over day-long sessions. This article covers how the pieces fit together, how to structure projects so incremental builds stay correct and fast, and the operational controls that keep the loop trustworthy.

## Scope

This article addresses watch mode and incremental compilation across common toolchains: change detection (file watching, dependency graph invalidation), build-oracle correctness (how tools decide what to rebuild), TypeScript project references with `--build --watch`, bundler watch/incremental modes (esbuild, Vite, webpack), and the failure modes of caches, watchers, and long sessions. It covers orchestration practice. It does not cover hot-module-reload runtime semantics, monorepo task-graph schedulers generally, or CI caching strategies (remote caches) except at the boundary.

## Workflow or implementation guidance

The anatomy of the loop has four stages:

1. **Detection.** A watcher (OS-level: inotify/FSEvents/ReadDirectoryChangesW; or polling fallback) reports file events. Detection is where correctness begins to leak: editors using atomic-save (write temp, rename) emit different events than in-place writes; network filesystems (NFS, some VM shares, WSL2 `/mnt/c`) often starve OS watchers, silently degrading tools to polling or to missing events entirely.
2. **Invalidation.** The tool's dependency graph maps changed files to affected outputs. Soundness varies by tool: TypeScript tracks imports precisely; bundlers track module graphs; CSS-in-JS and codegen pipelines sometimes have *undeclared* edges (a codegen step reading a schema the build file doesn't know about) — the classic "I regenerated the schema but nothing rebuilt" staleness.
3. **Rebuild.** Incremental engines reuse prior work at the granularity they support (function-level for Rust, file/declaration-level for TypeScript, module-level for bundlers) and write caches (`.tsbuildinfo`, `node_modules/.cache`, `target/`) that the *next* session also reuses — so a corrupted or version-skewed cache outlives the session that corrupted it.
4. **Reload.** Dev servers push updates (HMR) or signal restart; test watchers rerun affected tests.

Orchestration practice that keeps the loop sound:

- **Declare every edge.** If a build step consumes an input the toolchain doesn't know about (codegen from proto/schema/GraphQL files, generated clients, env manifests), wire it as a real dependency: a `tsc -b` composite project for generated TS, a bundler plugin reading the schema, or a task runner step the watcher owns. Undeclared edges are the root cause of most "stale build" mysteries.
- **Composite projects for multi-package TS.** TypeScript project references (`composite: true`, referenced paths) plus `tsc -b --watch` give per-project `.tsbuildinfo` and rebuild only downstream references — the mechanism that scales watch across a large repo. Without references, one giant `tsconfig` rechecks the world on every edit.
- **One watcher owns codegen.** When generated code feeds compilation, run the generator as a watched process that writes then triggers the compiler (directly or via output-file watching), and ensure generated output is either fully gitignored (rebuilt from source always) or committed (never regenerated locally) — mixing both regimes is where teams get conflicting stale artifacts.
- **Respect watcher limits.** Linux inotify has per-user watch limits (`fs.inotify.max_user_watches`); big monorepos exceed defaults and tools either fail loudly (good) or poll slowly (bad). Provision limits on dev images and document it; prefer tools that surface the failure.
- **Network-filesystem rule.** Source on NFS/VM-shared folders: configure polling (`usePolling` in webpack/vite configs, `CHOKIDAR_USEPOLLING=1` env) or move sources into the native filesystem (the standard WSL2 advice: keep the repo in the Linux filesystem, not `/mnt/c`). Polling costs CPU but correctness wins; decide per-environment, default to correctness.
- **Session hygiene.** Day-long watch sessions accumulate memory (retained module graphs, HMR state, leaked listeners). Accept restarts as routine: a `make dev-restart` that kills and relaunches the tree of watchers is a better daily tool than heroic debugging of a wedged watcher. Some tools (bundlers especially) degrade subtly before failing — slow rebuilds late in a session are a restart signal.
- **Cache versioning and resets.** Caches carry tool-version keys; after toolchain upgrades, verify the cache was invalidated (most tools handle it; the ones that don't produce bizarre one-off errors that vanish after cache deletion). Keep a documented cache-reset command per repo (`rm -rf node_modules/.cache **/*.tsbuildinfo`) for onboarding and incident triage; treat "delete the caches" as a legitimate fix, not an admission of failure — but log every time you needed it, because frequent resets indicate a real bug worth filing upstream or fixing in config.

Correctness verification discipline: the inner loop is fast, and speed breeds trust — so verify the loop itself periodically. The minimal check: make a semantic change that must alter output (rename an exported symbol used elsewhere), confirm the watch rebuild catches the *dependent* file too, not only the edited one; and periodically run a clean full build in CI (no incremental caches, fresh checkout) so drift between incremental output and from-scratch output — the scariest failure class, where dev builds and CI builds disagree — is caught by construction, not by a 3 a.m. debugging session.

A worked example: a monorepo with `packages/db` (generated from SQL schema), `packages/shared` (TS), and `apps/web` (Vite). The orchestration: `sqlc watch` regenerates `packages/db/src/generated/` (fully gitignored); `tsc -b packages/shared --watch` compiles shared with project references into `dist/` that web resolves; Vite dev server watches web sources and HMRs. Edits to the SQL schema regenerate db, which downstream consumes via declared package imports — every edge declared, every watcher scoped. A new engineer on WSL2 with sources under `/mnt/c` sees missed-rebuild symptoms on day one; the documented fix (move to Linux fs, or set polling) resolves it in minutes because the failure mode is documented, not mysterious.

## Controls

- Every build input is a declared dependency of its consumer (project reference, plugin, or owned watch step); PR review question for any new codegen: "which watcher rebuilds this?"
- Generated-code regime is uniform per repo (all gitignored or all committed), stated in the README; a CI check rejects a mix.
- CI runs at least one from-scratch (cache-free) build per day or per release branch to detect incremental-vs-clean drift.
- Dev environment docs cover watcher limits (inotify), polling for shared/network filesystems, and the WSL2 filesystem guidance; onboarding includes the "semantic change propagation" verification once, so every engineer knows how to prove their loop is sound.
- A `make clean-caches` target exists and its usage is logged/trended; rising usage opens investigation rather than normalization.

## Validation evidence

- TypeScript project references, composite builds, `.tsbuildinfo` incremental state, and `--build --watch` semantics are documented in the official TypeScript handbook (project references, incremental compilation) published at typescriptlang.org.
- Bundler watch/incremental behavior (webpack caching, Vite dependency pre-bundling and invalidation, esbuild incremental/context rebuilds) is documented in each tool's official docs; watcher behavior and polling options follow the chokidar model documented across the JS toolchain.
- A reproducible soundness check on any repo: edit an exported symbol in a leaf package, save, and within one rebuild cycle assert the downstream consumer's output changed; then run a clean build and diff against the watched build's outputs — zero diff is the incremental engine's core correctness claim, tested in your own setup.

## Failure modes and correction

- **Stale outputs from undeclared edges.** Symptom: changed schema, unchanged generated client. Correct by declaring the dependency or moving generation into an owned watcher.
- **Silent polling degradation / missed events.** Symptom: rebuilds only trigger on manual touch; CPU idle. Correct by filesystem placement or polling configuration; verify with the propagation check.
- **Corrupted or version-skewed caches.** Symptom: inexplicable errors after tool upgrades, resolved by cache deletion. Correct by reset runbook and, if recurring, upstream issue with reproduction.
- **Watch limits exhausted.** Symptom: "ENOSPC: inotify watch limit reached" or quiet partial watching. Correct by raising limits in dev images; prefer loud failure.
- **Day-long session degradation.** Symptom: rebuild latency creeps from 300 ms to 5 s. Correct by routine restart tooling; treat as maintenance, not debugging.

## Limitations

- Incremental soundness is per-toolchain; a sound TypeScript graph cannot save an unsound consumer (a script importing output by path outside the graph).
- Cross-repo dependencies (watching an installed sibling via `file:` links) strain invalidation logic; monorepo task orchestration handles this better than ad hoc watching.
- Watchers add load on huge trees; very large repos sometimes trade watch granularity for coarse rebuilds.
- Correct-but-slow (polling) versus fast-but-fragile (OS events on odd filesystems) is an environment decision without a universal default.

## Canonical sources

- Microsoft, TypeScript Handbook — Project References and Incremental compilation (`--build`, `--watch`, `.tsbuildinfo`): https://www.typescriptlang.org/docs/handbook/project-references.html
- Microsoft, TypeScript documentation — configuring watch mode (`watchOptions`, assumed changes): https://www.typescriptlang.org/docs/handbook/configuring-watch.html
