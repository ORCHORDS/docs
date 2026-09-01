# Ruff Unified Lint and Format Configuration for Python

Ruff consolidated Python code quality: one Rust binary implementing dozens of linters (pyflakes-class bug checks, pycodestyle, isort-style import sorting, pydocstyle, bugbear heuristics, and more) plus a Black-compatible formatter. For teams, the win is not only speed but *unification*: one `[tool.ruff]` configuration governs lint and format, one tool in pre-commit and CI, one source of truth for rules. The engineering work is choosing a rule set deliberately, configuring exclusions honestly, and preventing the two classic failure modes — rule sprawl (every rule someone liked) and silent narrowing (ignores accumulating until the tool checks nothing). This article covers configuring Ruff as the single quality gate, rule-family selection, per-file ignores, and CI/pre-commit integration.

## Scope

This article addresses Ruff configuration and adoption: `pyproject.toml` `[tool.ruff]` (and `ruff.toml`) settings — `lint.select`, `lint.ignore`, `per-file-ignores`, formatter interaction with lint rules (`E501` interplay), `lint.fixable`/`unfixable`, extension rules requiring opt-in (`B`, `SIM`, `UP`, `D` docstrings), and the `ruff check` / `ruff format` command pair in CI and pre-commit. It does not cover mypy/type-checking policy, pytest conventions, or migration strategies from full legacy toolchains beyond the mapping basics.

## Workflow or implementation guidance

Ruff has two commands with separated concerns: `ruff check` (lint: rule violations, many auto-fixable) and `ruff format` (format: one canonical style, Black-compatible, minimal configurability by design). They compose: format first, lint second, and the lint rule set must not fight the formatter.

A production-grounded configuration sequence:

1. **Start with the ecosystem-default baseline**: `select = ["E4", "E7", "E9", "F"]` (pycodestyle subset + pyflakes) is Ruff's default because it is nearly uncontroversial — undefined names (`F821`), unused imports (`F401`), syntax errors. Ship that green before expanding.
2. **Expand by rule family with a team decision per family.** The families that earn their CI cost:
   - `B` (flake8-bugbear): probable-bug heuristics — mutable default arguments (`B006`), unused loop variables, `assert` in production paths (`B011`). High value, occasional false positives needing `noqa` with justification.
   - `UP` (pyupgrade): modernize syntax (`Optional[X]` → `X | None` on supported versions). One-time churn, then keeps the codebase current. Gate on your minimum Python version (`target-version`), which Ruff reads from `pyproject.toml` `requires-python`.
   - `SIM` (flake8-simplify): compressible patterns (use `is` for None, collapse nested ifs). Cosmetic-leaning; some teams skip.
   - `I` (isort): import ordering. Pairs with the formatter — enable and stop arguing about imports forever. Configure `lint.isort.known-first-party` for your package names.
   - `D` (pydocstyle): docstring presence/style — valuable for library code, noisy for applications. If adopted, restrict via `lint.pydocstyle.convention = "google"` (or pep257/numpy) to kill configuration degrees of freedom.
   - Security-family rules (Ruff implements a subset of bandit `S` rules): flag `exec`, hardcoded temp paths, weak hash usage in security contexts. Adopt selectively — `S` flags like `S101` (use of assert) conflict with test suites and belong in `per-file-ignores` for `tests/`.
3. **Line length and the formatter.** `ruff format` enforces line length as *formatting*; keeping `E501` (line-too-long) in lint double-reports. Ruff's default: `E501` is in the ignore set when the formatter handles length — keep that arrangement; do not re-enable `E501` while using the formatter.
4. **`per-file-ignores` for real exceptions.** Test suites legitimately use asserts (`S101`, `B011`), `__init__.py` re-exports (`F401`), generated code gets everything. Pattern them explicitly:
   ```toml
   [tool.ruff.lint.per-file-ignores]
   "tests/**" = ["S101"]
   "**/__init__.py" = ["F401"]
   "src/gen/**" = ["ALL"]
   ```
   Per-file ignore is the honest mechanism; global `ignore` for a rule used in one context mutes it everywhere.
5. **Fix policy.** Many rules are auto-fixable; `ruff check --fix` applies safe fixes, `--unsafe-fixes` the rest (unsafe = the fix is plausible but can change behavior; a comment diff review belongs in the PR that introduces them). In CI run without `--fix` (gate mode); in pre-commit run with safe `--fix` (convenience mode) so the gate and the helper stay consistent.
6. **Version pinning.** Ruff adds and occasionally retriggers rules on version bumps (preview-mode rules especially). Pin the exact version in pre-commit config and CI; upgrade deliberately with a diff of newly-firing rules, like any dependency.
7. **Legacy migrations.** Ruff ships config migration from flake8/isort setups; the rule-code mapping is documented (flake8 `E`/`F`/`W` map directly; plugin prefixes map to their families). Migrate configs mechanically, then run the gate, fix or `noqa` the backlog in a dedicated "quality baseline" PR so feature PRs start clean — never mix baseline fixes with feature work.

A worked example: a service codebase on flake8+isort+black with three config files collapses to one `[tool.ruff]` block. The team selects `E4,E7,E9,F,B,UP,I` plus `S` security subset with tests exempted via per-file-ignores. CI runs `ruff format --check` then `ruff check` (fail on any violation); pre-commit runs both with fix. The baseline PR fixes 214 auto-fixables and justifies 11 `noqa`s in review. Afterward, a rule-family addition (`SIM`) is a two-line PR whose diff shows every proposed change — rules debated with evidence, not vibes.

The `noqa` discipline makes or breaks the gate: Ruff supports `# noqa: B008` (suppress with reason optional via `--extension` settings but conventionally the code alone), and `ruff check --statistics` reports violation counts. Require justification comments for suppressions (`# noqa: B006  # deliberate shared cache`) in review; track the count like test skips.

## Controls

- One configuration file for the repo (`pyproject.toml` preferred); CI asserts the file exists and pre-commit/CI/editor all invoke the same pinned ruff version (`ruff --version` echoed in job logs).
- Gate order in CI: `ruff format --check` → `ruff check` → tests; formatting failures fail fast before slower stages.
- Global `ignore` entries require a written rationale in a comment on the same line; per-file-ignores preferred; `ALL` ignores allowed only in generated-code paths.
- `noqa` lines require adjacent justification and are counted in CI output (`grep -rn noqa src | wc -l`) and trended; a rising count triggers review.
- Rule-family additions go through their own PRs (config diff + resulting violations diff) so reviewers see the cost of each family before accepting it.

## Validation evidence

- Rule families, rule codes and their fixability/safety classes, the `select`/`ignore`/`per-file-ignores` schema, formatter behavior and its deliberate incompatibility list (including the E501 interplay), `--fix`/`--unsafe-fixes` semantics, and config migration from flake8/isort are documented in the official Ruff documentation at docs.astral.sh.
- The tool's Black-compatibility claims for `ruff format` are documented with the explicit deviations list — the contract that lets teams replace Black without a mass reformat.
- A reproducible check: on a scratch file with `import os` (unused), `def f(x=[]): ...` (mutable default), and a 120-char line, run the pinned `ruff check` and `ruff format --check`; observe F401 and B006 flagged, the long line handled by the formatter not E501; apply `--fix` and watch F401 vanish while B006 remains (not safely auto-fixable) — validating gate, fix policy, and formatter interplay in one pass.

## Failure modes and correction

- **Rule sprawl.** Symptom: every rule someone liked is on; PRs drown in style churn. Correct by family-level PRs with cost visible in the diff.
- **Silent narrowing.** Symptom: `ignore` list grows across PRs; gate weakens unnoticed. Correct with rationale-comments-on-ignore policy and CI reporting the effective rule count.
- **Unpinned ruff.** Symptom: CI flips red overnight on new rules. Correct by exact version pin and deliberate upgrades.
- **Unsafe fixes in CI.** Symptom: behavior changed by auto-fix. Correct by reserving `--unsafe-fixes` for reviewed local runs, never CI.
- **Fighting the formatter.** Symptom: E501 or import-order lint noise the formatter contradicts. Correct by deferring to the formatter (drop E501; keep isort rules aligned with format output).

## Limitations

- Ruff is syntactic and heuristic: it does not type-check (pair with mypy/pyright) or run code; type-confusion bugs pass every rule.
- Preview-mode rules and newly implemented linters shift between versions even outside major bumps; pinned upgrades are mandatory, not optional.
- The formatter offers few knobs by design; teams needing configurable formatting (line wrapping policy beyond length) must accept its opinions or not adopt it.
- Some legacy plugin behaviors map imperfectly; a migration audit PR (before/after violation diff) is the honest way across.

## Canonical sources

- Astral, Ruff documentation (configuration, rules, formatter, commands): https://docs.astral.sh/ruff/
- Python packaging norms for `pyproject.toml` tool configuration: Python Packaging User Guide, https://packaging.python.org/
