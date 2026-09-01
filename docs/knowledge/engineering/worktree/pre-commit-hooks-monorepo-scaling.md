# Scaling the pre-commit Framework Across a Large Monorepo

## Scope

This article covers running the pre-commit framework (pre-commit.com) in monorepos where full-tree hooks collapse: keeping commit latency inside a human tolerance, partitioning hooks with path filters, maintaining per-hook isolated environments cheaply, and keeping the tool's own update cadence from breaking every developer at once. It applies to repositories with hundreds of thousands of files and polyglot trees. It does not cover choosing between hook frameworks, server-side pre-receive enforcement, or commit-message linting design.

## Workflow or implementation guidance

The pre-commit framework's contract is worth stating precisely because every scaling decision follows from it: on each `git commit`, pre-commit stashes unstaged changes, copies staged files into a temporary area, runs each hook as a process against those files, and re-applies the stash. Two costs scale badly in a monorepo. First, hook runtime: a hook invoked once with all staged filenames beats the same hook invoked per-file, but a hook with no path filter still runs against any commit that touches anything. Second, environment install: each hook with `language: python` or `language: node` gets its own virtualenv or node_modules on first run, and a monorepo that accumulates a dozen hooks accumulates a dozen environments.

**Partition aggressively with `files` and `exclude`.** The single highest-leverage change. Every hook declaration should carry a `files:` regex narrowing it to its territory:

```yaml
- id: ruff
  files: ^services/api/.*\.py$
- id: eslint
  files: ^apps/web/.*\.(ts|tsx)$
- id: shellcheck
  files: ^scripts/.*\.sh$
```

A Python-only hook that runs for a docs commit is pure latency. The complement is `exclude:` for generated trees (`^third_party/`, `^dist/`). Budget the whole pre-commit run: a reasonable target is that `git commit` completes within ten seconds for a typical change; beyond roughly thirty, developers reach for `--no-verify`, and at that moment the hook suite becomes decoration. Measure with `pre-commit run --show-diff-on-failure` timing output or a simple `time git commit` on representative staged changes.

**Use `stages` and keep default stages lean.** Hooks that only make sense pre-push (expensive type checks, full test shards) belong at `stages: [pre-push]`, not pre-commit. The framework will happily run everything at commit time if you let it; the config must say otherwise.

**Pin revisions and stage updates through CI, not developer machines.** The `rev:` field pins each hook's repository commit. If every developer's pre-commit auto-updates independently, you get "works on my machine" lint results. Instead: pin `rev:` in `.pre-commit-config.yaml`, let the periodic CI job (`pre-commit autoupdate` on a scheduled branch) propose bump PRs, and treat hook updates as reviewable changes. Developers never run `autoupdate` locally as part of normal work.

**Cache environments.** The framework caches installed hook environments under `~/.cache/pre-commit` (location varies by OS; Git Bash on Windows keeps it under the user profile). CI should cache that directory keyed on the config hash, so a matrix of jobs does not rebuild every virtualenv per run. Local first-run slowness is acceptable and one-time; recurring slowness means the cache is being invalidated — usually because `rev:` churns weekly.

**Handle the partial-staging subtlety.** Because the framework runs against staged content only, a developer who stages half a file (`git add -p`) gets hooks judging that half-file. A formatter that rewrites the staged copy produces a tree where staged and working copies diverge confusingly. The practical rule to teach: when a hook modifies files (autofix), re-stage (`git add -u <paths>`) before retrying the commit; when mid-way through interactive staging, run `pre-commit run --files <path>` on the full file first, then stage hunks. This is the most common "pre-commit ate my commit" support ticket, and it is a model issue, not a bug.

**Local hooks for repo-specific checks.** Repo-local hooks (`repo: local`) let you wire monorepo-aware checks without publishing a hook repo — for example, a script that resolves the affected workspace via `git diff --cached --name-only` and runs only that workspace's linter. Keep these fast and dependency-light; a local hook that shells into a full build is a latency regression disguised as rigor.

## Controls

- Every remote hook declares a `files:` (or documented rationale for none); the config review checklist rejects unfiltered hooks.
- Default `stages` contain only fast checks; anything above ~5 seconds runtime moves to `pre-push` or CI.
- `rev:` fields are pinned; updates flow exclusively through scheduled CI autoupdate PRs with green runs before merge.
- Hook environments are cached in CI keyed on config hash; cold-cache CI time is tracked so environment bloat is visible.
- Generated and vendored trees are listed once in a shared `exclude` and reused across hooks.
- Commit latency is measured periodically (`time pre-commit run --all-files` on a canary change); exceeding the ten-second typical / thirty-second worst-case budget opens a trimming task.

## Validation evidence

- `pre-commit run --files docs/example.md` completes with only docs-relevant hooks executing — path partitioning proven by observing which hooks report.
- A deliberately slow change (staging files across three languages) commits within the latency budget; timing recorded in the repo's benchmarks file.
- A scheduled autoupdate PR that bumps a hook `rev:` shows CI catching a new lint rule violation — evidence the update path is review-gated, and that new rules cannot land unobserved.
- Partial-staging drill: `git add -p` half a file with a formatting error in the unstaged half, commit, and observe the framework stashing behavior; document the exact re-stage recovery steps for onboarding.
- Fresh-clone onboarding: `pip install pre-commit && pre-commit install` from the README, followed by one commit, completes within the first-run install budget (environments build once, cache hits thereafter on the second commit).
- `pre-commit validate-config` passes in CI, preventing YAML drift (typo'd `files:` regexes that silently match nothing).

## Failure modes and correction

- **The `--no-verify` bypass spiral.** Latency creeps past thirty seconds; developers bypass; broken commits reach CI which now catches what pre-commit should have. Correction: re-trim to budget, and pair the local suite with a matching CI job so bypassing costs minutes of CI rather than zero.
- **Silent no-op regex.** A `files:` pattern with a typo matches nothing, and the hook appears green while checking nothing. Correction: `pre-commit validate-config` plus a periodic canary that stages a file the hook must flag and asserts it fails.
- **Environment drift between developers.** One developer's cache holds an old `rev:` environment; results disagree across machines. Correction: `pre-commit clean` documented in bootstrap; the pinned-rev-via-CI policy prevents recurrence.
- **Autofix interleaved with interactive staging.** Staged and working copies diverge after a hook rewrites the staged snapshot, and the developer commits a half-state. Correction: teach the re-stage rule; for teams that hit it often, move pure formatters to a `post-checkout`/manual `pre-commit run` flow or an editor-on-save hook.
- **Local hook creep.** Repo-local hooks accrete until each shells out to a full toolchain; the suite doubles in latency over a quarter. Correction: the periodic latency benchmark makes creep visible; local hooks face the same budget as remote ones.
- **Windows path and line-ending surprises.** Hooks written for POSIX paths or LF assumptions misfire in Git Bash checkouts. Correction: hooks receive filenames from the framework — test one hook on Windows in CI matrix before adopting it repo-wide.

## Limitations

The framework runs client-side, so it is advice, not enforcement: any developer can bypass it, and true gating requires CI or server-side hooks — pre-commit's own design accepts this explicitly. Latency budgets depend on hardware spread; a ten-second budget on the maintainers' laptops may be thirty on the intern's. Environment isolation per hook means shared dependencies install repeatedly; that is the price of reproducibility and does not shrink. The stash/restore dance around staged content cannot inspect unstaged files by design, so whole-file semantic checks (some type checkers) give approximate answers at commit time and remain better suited to pre-push or CI. On very large staged changes (thousands of files, e.g. a vendored tree import), even partitioned hooks can take minutes; big mechanical commits warrant an explicit, reviewed bypass rather than a silent one.

## Canonical sources

- pre-commit framework documentation (hooks configuration, files/exclude, stages, caching): https://pre-commit.com/
- pre-commit framework — usage and supported hooks details: https://pre-commit.com/#usage
- Git documentation — githooks (pre-commit and pre-push hook contracts): https://git-scm.com/docs/githooks
- pre-commit CI service (managed, cache-backed runs of the same config): https://pre-commit.ci/
