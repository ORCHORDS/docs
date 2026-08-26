# Git Hooks Sequential vs Parallel Execution Strategy

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your `pre-commit` hook takes 25–40 seconds because lint, type-check, and test
all run one after another. Developers start skipping hooks with `--no-verify`.
Alternatively, a naively parallelised hook intermingles stdout/stderr, making
failures impossible to read, and leaves orphan processes when any one check
exits non-zero.

---

## Context

Git hooks are ordinary shell scripts. Git itself calls them synchronously and
waits for an exit code before proceeding. The _internal_ structure of each hook
script is entirely under your control: steps can be sequential, background-
parallel with `wait`, or orchestrated through a runner like Lefthook or
`turbo run`.

In the example project Cloudflare Workers monorepo (pnpm workspaces + Turborepo) most
hooks gate the `pre-commit`, `commit-msg`, `pre-push`, and `prepare-commit-msg`
stages. The trade-off between sequential and parallel is:

| Concern | Sequential | Parallel |
|---|---|---|
| Wall-clock time | Slow (sum of steps) | Fast (max of steps) |
| Output readability | Clean | Interleaved unless buffered |
| Resource usage | Low | High – all CPUs |
| Early exit behaviour | First failure stops immediately | Must `wait` and aggregate |
| Orphan process risk | None | Must `trap` + kill group |

---

## Profiling existing hooks

Before rewriting anything, measure each step:

```bash
# .git/hooks/pre-commit (temporary instrumentation)
set -euo pipefail
_t() { local s=$SECONDS; "$@"; echo "[$?] $* took $((SECONDS-s))s" >&2; }

_t pnpm lint-staged
_t pnpm tsc --noEmit -p tsconfig.json
_t pnpm vitest run --reporter=dot
```

Run `git commit --allow-empty -m "bench"` three times and average. Steps
exceeding 5 s independently are candidates for parallelisation.

---

## Sequential baseline (simple, correct)

The safest starting point: fail fast, output is clean, exit codes are
unambiguous.

```bash
#!/usr/bin/env bash
# .git/hooks/pre-commit
set -euo pipefail
export FORCE_COLOR=1

echo "==> lint-staged"
pnpm lint-staged

echo "==> type-check"
pnpm --filter '@example project/*' exec tsc --noEmit

echo "==> unit tests (changed packages only)"
pnpm turbo run test --filter='[HEAD^1]' -- --reporter=dot
```

When a step fails the hook exits immediately (set -e) and git aborts the
commit. Total time: sum of all steps.

---

## Parallel execution with process groups

Run long-independent steps concurrently, capture output per-job, print on
failure only.

```bash
#!/usr/bin/env bash
# .git/hooks/pre-commit — parallel variant
set -uo pipefail
export FORCE_COLOR=1

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"; kill 0' EXIT  # kill entire process group on exit

run_job() {
  local name=$1; shift
  local log="$TMPDIR/$name.log"
  "$@" >"$log" 2>&1 &
  echo $!  # return pid
}

# Fire all jobs
PID_LINT=$(run_job lint      pnpm lint-staged)
PID_TSC=$(run_job  tsc       pnpm exec tsc --noEmit -p tsconfig.json)
PID_TEST=$(run_job test      pnpm turbo run test --filter='[HEAD^1]' -- --reporter=dot)

# Collect results
EXIT=0
for entry in "lint:$PID_LINT" "tsc:$PID_TSC" "test:$PID_TEST"; do
  name=${entry%%:*}
  pid=${entry##*:}
  if ! wait "$pid"; then
    echo "FAILED: $name" >&2
    cat "$TMPDIR/$name.log" >&2
    EXIT=1
  fi
done

exit $EXIT
```

Key points:
- `trap 'kill 0'` sends SIGTERM to every process in the group on early exit.
- Logs are buffered per job; only failures are printed (no interleaving).
- `set -u` (but NOT `-e`) so the loop continues collecting all failures.

---

## Lefthook parallel groups

[Lefthook](https://github.com/evilmartians/lefthook) expresses the same
pattern declaratively. It is already installed as a devDependency in the root
`package.json`.

```yaml
# lefthook.yml
pre-commit:
  parallel: true          # all commands in this hook run in parallel
  commands:
    lint:
      run: pnpm lint-staged
      fail_text: "Lint failed — run `pnpm lint-staged` to reproduce"
    tsc:
      run: pnpm exec tsc --noEmit -p tsconfig.json
      fail_text: "Type errors found — run `pnpm tsc` to reproduce"
    test:
      run: pnpm turbo run test --filter=[HEAD^1] -- --reporter=dot
      fail_text: "Tests failed — run `pnpm test` to reproduce"

commit-msg:
  parallel: false         # must be sequential — reads COMMIT_EDITMSG
  commands:
    commitlint:
      run: pnpm commitlint --edit {1}
```

Install / update the git hooks:

```bash
pnpm exec lefthook install
```

Lefthook buffers stdout per command and streams the combined report only after
all jobs finish (or any one fails, depending on `--force-colors` mode).

---

## Selective parallelism: what MUST stay sequential

Some hooks cannot safely parallelise their internal steps:

| Hook | Must-sequential step | Reason |
|---|---|---|
| `commit-msg` | commitlint | Reads `$1` (COMMIT_EDITMSG path) passed by git |
| `prepare-commit-msg` | template injection | Mutates the message file in place |
| `pre-push` | build then deploy | Build artifact must exist before deploy |
| `pre-commit` | lint-staged + test | Lint mutates staged files; test must see final state |

`lint-staged` in particular rewrites staged files then re-stages them. Running
it in parallel with `tsc` can cause tsc to see a half-staged working tree. Fix:
run lint-staged first (sequential), then parallelise tsc + tests.

```yaml
# lefthook.yml — mixed strategy
pre-commit:
  parallel: false
  commands:
    a_lint_staged:           # prefix with 'a_' to control lexicographic order
      run: pnpm lint-staged
      priority: 1
    b_parallel_checks:
      run: pnpm exec lefthook run _pre-commit-parallel --no-install
      priority: 2

_pre-commit-parallel:        # synthetic hook, called programmatically
  parallel: true
  commands:
    tsc:
      run: pnpm exec tsc --noEmit
    test:
      run: pnpm turbo run test --filter='[HEAD^1]'
```

---

## CI parity: mirror hook parallelism in Actions

Your local parallel hooks should map to a matching GitHub Actions matrix so
that CI reproduces the same isolation:

```yaml
# .github/workflows/pr-checks.yml
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pnpm lint-staged --diff="origin/${{ github.base_ref }}...HEAD"

  type-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pnpm exec tsc --noEmit

  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pnpm turbo run test --filter='[${{ github.event.pull_request.base.sha }}]'
```

All three jobs run in parallel inside GitHub Actions automatically.

---

## Anti-patterns

- **`set -e` in a parallel collector loop** — exits on the first `wait` failure,
  orphaning remaining background processes. Use `set -uo pipefail` and track
  `$EXIT` manually.
- **Unbuffered parallel output** — interleaved lint errors and tsc errors are
  unreadable. Always redirect each job to a temp file.
- **Running `lefthook run` inside a lefthook hook** without `--no-install` —
  triggers recursive hook reinstallation.
- **Not trapping signals** — a Ctrl-C during a parallel hook leaves tsc and
  vitest processes running in the background consuming CPU.
- **Parallelising commit-msg validation** — commitlint must run after git
  writes the message file; there is nothing to parallelise here.

---

## Gotchas

- `kill 0` kills the entire process group including the terminal's own shell on
  some CI runners. Use `kill -- -$$` (kill the hook's own group) instead when
  inside GitHub Actions.
- Lefthook `parallel: true` spawns goroutines, not subshells, so POSIX `trap`
  inside individual `run:` scripts does NOT propagate to the Lefthook process.
- `pnpm turbo run test --filter='[HEAD^1]'` returns exit 0 even when no
  packages match the filter. Add `--filter='[HEAD^1]' | grep -q .` or use
  `turbo run test --filter='[HEAD^1]' --only` to guard against silent no-ops.
- On macOS, `mktemp -d` requires `-t prefix` form; on Linux the form above
  works. Use `TMPDIR=$(mktemp -d 2>/dev/null || mktemp -d -t 'hooks')` for
  portability.

---

## Verification

```bash
# 1. Measure wall-clock time of sequential vs parallel hooks
time git commit --allow-empty -m "test: benchmark hooks"

# 2. Confirm all three jobs ran (lefthook prints a summary table)
# Expected output includes: ✔ lint, ✔ tsc, ✔ test

# 3. Introduce a type error and verify parallel mode still reports it
echo 'const x: number = "oops"' >> packages/api/src/index.ts
git add packages/api/src/index.ts
git commit -m "test: type error"
# Expected: hook exits non-zero, tsc log printed, commit aborted
git checkout -- packages/api/src/index.ts

# 4. Confirm orphan protection: Ctrl-C during hook leaves no vitest processes
ps aux | grep vitest  # should be empty after Ctrl-C
```

---

## Related

- `documentation/categories/worktree/git-hooks-lefthook-monorepo.md`
- `documentation/categories/worktree/git-hooks-husky-lint-staged-commitlint.md`
- `documentation/categories/worktree/pre-commit-hooks-comparison-2026.md`
- `documentation/categories/worktree/pre-push-hooks-comprehensive-validation.md`
- `documentation/categories/worktree/monorepo-ci-parallelization.md`

---

## Sources

- Lefthook documentation — https://github.com/evilmartians/lefthook/blob/master/docs/reference/lefthook_yml.md
- Git SCM Book: Customising Git — https://git-scm.com/book/en/v2/Customizing-Git-Git-Hooks
- GNU Bash manual: Job control — https://www.gnu.org/software/bash/manual/bash.html#Job-Control
- lint-staged README: parallel lint and type-check caveat — https://github.com/lint-staged/lint-staged#running-multiple-commands-in-a-sequence
