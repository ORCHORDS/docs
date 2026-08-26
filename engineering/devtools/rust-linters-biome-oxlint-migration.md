# rust-linters-biome-oxlint-migration

**Issue:** A typical 2024-era JavaScript/TypeScript repo lints with ESLint (flat config, dozens of plugins, 100+ npm packages) and formats with Prettier — a slow, two-tool, 150-package devDependency tree that adds minutes to CI. In 2025 the Rust-based replacements matured (Biome 2.x and Oxlint 1.0 + Oxfmt, both with automated ESLint/Prettier migration commands), and teams are now actively consolidating. This article covers the current landscape, the concrete migration paths for both tools, and how to choose between them.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 2025-2026 landscape

1. **Biome 2.x is the integrated all-in-one.** One binary, one `biome.json`, doing linting, formatting, import organizing, and assist actions — reported 10-25x faster than the ESLint+Prettier pair while collapsing ~127 npm packages into a single dependency. Biome 2 added type-aware lint rules with its own multi-file type inference, reducing the last big gap versus typescript-eslint.
2. **Oxlint 1.0 (August 2025) is the speed champion.** Built on the Oxc toolchain, it is reported 50-100x faster than ESLint, with a companion formatter (`oxfmt`) covering the Prettier role. It deliberately focuses on correctness-critical rules and scales to monorepos where ESLint's startup cost dominates.
3. **Automated migration is now table stakes.** `biome migrate eslint` / `biome migrate prettier` and `oxlint migrate eslint` both parse existing configs (including nested and legacy formats) and emit the new config plus a report of rules they could not map — the era of hand-porting rule lists is over.
4. **ESLint is not dead.** The typescript-eslint and plugin ecosystem (React, Next.js, Vue, import, jest, a11y) still has the widest rule coverage, so the common 2026 pattern is a hybrid: fast Rust linter as the always-on first pass, ESLint retained only for the few type-aware or plugin-specific rules nothing else implements yet.
5. **Decision drivers are now speed, config count, and rule coverage — in that order for most teams.** CI lint time is the visible cost; the invisible cost is the flat-config churn and plugin upgrade matrix that the single-binary tools eliminate entirely.

## Migrating to Biome

1. **Run `npx @biomejs/biome migrate eslint --write`.** Biome converts flat configs, legacy `.eslintrc` files, and even nested per-folder configs into the unified `biome.json`, and prints an unmapped-rules report at the end — that report becomes your TODO list, not a silent behavior change.
2. **Run `npx @biomejs/biome migrate prettier --write` for formatting parity.** It imports `.prettierrc` options (line width, quotes, semicolons, trailing commas) so the formatter's output stays close to the existing code style and your migration diff stays reviewable.
3. **Adopt the extras ESLint never had natively.** `biome check --write` runs lint safe-fixes, unsafe fixes (opt-in), import organizing (`organizeImports`), and formatter in a single pass; wire it as `"lint": "biome check ."` and delete the parallel `prettier --write` and `lint-staged` formatting legs.
4. **Handle rule gaps explicitly.** For unmapped rules, either accept the coverage loss, suppress with inline `// biome-ignore lint/suspicious/noXxx: reason` comments, or keep a minimal residual ESLint config with only the missing plugins — but measure first; most teams find fewer than a handful of rules actually mattered.
5. **Repoint the editor.** Install the official VS Code Biome extension, set it as `editor.defaultFormatter` and enable code-actions on save, and remove the ESLint/Prettier extensions from the workspace recommendations so the two stacks do not fight over the same files.

## Migrating to oxlint + oxfmt

1. **Start with `npx oxlint migrate eslint`.** The migration tool reads the ESLint config and emits `.oxlintrc.json` using its plugin-name mapping (`@typescript-eslint` rules to the `typescript` plugin, `eslint-plugin-react` to `react`, etc.), plus a list of unsupported features to review.
2. **Use it as a first-pass linter in a hybrid setup.** The officially recommended pattern: run oxlint (fast, no type info needed) over the whole repo, then run the residual typescript-eslint/ESint pass only if oxlint passes — CI time drops because the expensive linter runs after the cheap one filters nothing (it exits early on oxlint failure) while keeping full rule coverage.
3. **Adopt oxfmt deliberately.** Replace Prettier by moving formatting to oxfmt and removing `.prettierrc`/`prettier` scripts; because formatting output differs slightly from Prettier, do the format switchover in a dedicated commit so style churn never mixes with logic changes in review.
4. **Audit the unsupported-features report.** Known gaps (specific plugin rules, complex `overrides` conditions, some type-aware rules) are documented in the migration guide; decide per-gap whether to drop the rule, keep it in residual ESLint, or wait — the report is deterministic, so re-running the migration after upgrades shows progress.
5. **Exploit the speed in CI and pre-commit.** Full-repo oxlint runs finish in a fraction of a second on typical repos, which makes whole-repo linting viable on every pre-commit hook (e.g. via pre-commit or lefthook) instead of only on changed files — catching in-flight violations before they ever reach a branch.

## Choosing between them

1. **Pick Biome for the integrated, one-tool future.** One config, one dependency, formatter included, import sorting included, assist actions included — best for new projects and teams tired of orchestrating multiple tools, at the cost of some opinionation and less plugin breadth than ESLint.
2. **Pick oxlint + oxfmt for maximal lint speed in an existing ESLint-heavy org.** Its hybrid-with-ESLint story is first-class, adoption is incremental (add it as pass #1, delete ESLint rules as they get covered), and it shines in monorepos where per-package lint invocations dominate CI time.
3. **Weigh type-aware rules carefully.** Biome 2's built-in type inference covers common cases without tsc; teams whose correctness depends on advanced typescript-eslint rules (e.g. `no-unsafe-*` strictness) will keep a residual typescript-eslint leg with either choice — budget for it.
4. **Check your framework-specific needs before committing.** Next.js, Vue, Svelte, and Solid projects live on framework plugins; verify the Biome/Oxlint rule sets (or community plugins) cover the rules your repo actually fails on today — grep the CI lint log before migrating, not after.
5. **Migrate in three commits: convert, reformat, delete.** Commit 1 lands the new config from the migrate tools; commit 2 applies the new formatter to the whole tree (mechanical, huge diff, `git log --ignore-all-space` friendly); commit 3 removes ESLint/Prettier packages, scripts, and editor settings. Each step is revertible and reviewable in isolation.
