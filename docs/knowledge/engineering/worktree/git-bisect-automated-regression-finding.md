# Git Bisect — Automated Regression Finding

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

A regression was introduced sometime in the last 200 commits, but you
do not know which one. Manually checking each commit takes hours. You
resort to reading diffs of "suspicious" commits, guessing which change
caused the bug, and testing one by one. The bug might have been
introduced weeks ago, and the commit that caused it touches code
unrelated to where the symptom appears.

## Context

`git bisect` uses binary search to find the exact commit that
introduced a regression. With 1,000 commits between "good" and "bad,"
bisect finds the culprit in ~10 steps instead of 500. When combined
with `git bisect run`, the entire process is automated — you provide a
test script, and Git walks the commit history, testing each midpoint
automatically. In 2026, automated bisecting is a standard debugging
technique, especially in repositories with clean commit history (linear
main branch, squash merges) where every commit is independently
buildable and testable.

## Manual bisect workflow

```bash
# Start bisecting
git bisect start

# Mark the current (broken) commit as bad
git bisect bad

# Mark a known-good commit (e.g., last release tag)
git bisect good v2.3.0

# Git checks out a midpoint commit
# Bisecting: 127 revisions left to test after this (roughly 7 steps)

# Test the checkout, then mark it
git bisect good   # if the bug is NOT present
# or
git bisect bad    # if the bug IS present

# Repeat until Git identifies the first bad commit
# abc1234 is the first bad commit
# commit <commit-sha>
# Author: ...
# Date: ...
#     Refactor payment validation logic

# Clean up when done
git bisect reset
```

## Automated bisect with `git bisect run`

```bash
# Automated: provide a test script
git bisect start
git bisect bad HEAD
git bisect good v2.3.0

# Run a test script at each step
# Exit code 0 = good, non-zero = bad, 125 = skip
git bisect run ./test-regression.sh

# Or use an inline command
git bisect run python -m pytest tests/test_payment.py::test_checkout_total

# Or use make/npm
git bisect run npm test -- --grep "calculates tax correctly"
```

### Test script example

```bash
#!/bin/bash
# test-regression.sh

# Build the project (skip if build fails — commit might not compile)
make build 2>/dev/null || exit 125

# Run the specific regression test
make test-unit TEST=test_checkout_total
exit $?

# Exit codes:
#   0   = good (bug not present)
#   1   = bad (bug present)
#   125 = skip (commit cannot be tested, e.g., build failure)
```

## Advanced patterns

### Bisecting with a custom test

```bash
# Find which commit introduced a performance regression
git bisect start
git bisect bad HEAD
git bisect good v2.0.0

git bisect run bash -c '
  npm run build &&
  time=$(npm run benchmark -- --json | jq ".duration") &&
  echo "Duration: $time ms" &&
  [ "$time" -lt 200 ]  # fail if benchmark > 200ms
'
```

### Bisecting across merge commits

```bash
# Skip merge commits that cannot be tested independently
git bisect start
git bisect bad HEAD
git bisect good v2.3.0

# If a merge commit does not build, skip it
git bisect run bash -c '
  make build 2>/dev/null || exit 125
  make test-specific || exit 1
'
```

### Bisecting with flaky tests

```bash
# Run the test multiple times to handle flakiness
git bisect run bash -c '
  PASSES=0
  for i in 1 2 3; do
    if npm test -- --grep "flaky test" 2>/dev/null; then
      PASSES=$((PASSES + 1))
    fi
  done
  # Majority vote: 2 out of 3 passes = good
  [ $PASSES -ge 2 ]
'
```

## Prerequisites for effective bisecting

```
1. Clean main branch
   → Every commit on main should build and pass tests
   → Protect main with required CI checks
   → Use squash merges for small PRs

2. Deterministic reproduction
   → Write a test that exits 0 (good) or 1 (bad)
   → The test must be self-contained and fast
   → Avoid tests that depend on external services

3. Buildable history
   → Every commit should compile/build independently
   → Lock files committed (dependencies reproducible)
   → No commits that break the build intentionally

4. Reasonable commit granularity
   → Squash or rebase for logical units of work
   → Avoid 1,000-line "fix everything" commits
   → Each commit should do one thing
```

## CI integration

```yaml
# GitHub Actions: automated bisect on regression report
name: Bisect Regression
on:
  workflow_dispatch:
    inputs:
      bad_ref:
        description: 'Bad commit/tag'
        required: true
      good_ref:
        description: 'Last known good commit/tag'
        required: true
      test_command:
        description: 'Test command (exit 0=good, 1=bad)'
        required: true

jobs:
  bisect:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - run: |
          git bisect start
          git bisect bad ${{ inputs.bad_ref }}
          git bisect good ${{ inputs.good_ref }}
          git bisect run ${{ inputs.test_command }}
```

## Anti-patterns

- **Bisecting without a reproducible test** — running `git bisect`
  and manually testing each commit by eye. This is slow, error-prone,
  and defeats the purpose of automation. Always write a script first.
- **Bisecting a dirty working tree** — having uncommitted changes
  during bisect causes checkout conflicts. Stash or commit changes
  before starting.
- **Full test suite as bisect script** — running the entire test
  suite at each bisect step. Bisect may run 10+ times; a 30-minute
  test suite makes this impractical. Write a focused test that
  takes seconds.
- **Bisecting across dependency changes** — if `node_modules` or
  build artifacts are not reproducible per commit, bisect fails at
  commits with different dependencies. Include `npm ci` or equivalent
  in the bisect script.

## Gotchas

- **Exit code 125 for unevaluable commits** — if a commit cannot
  be tested (e.g., build failure), the script must return exit code
  125, not 1. Returning 1 tells Git the commit is "bad," which
  skews the binary search.
- **Merge commits complicate bisect** — merge commits may not
  represent a buildable state if the merge introduced conflicts that
  were resolved. Linear history (rebase/squash) produces cleaner
  bisect results.
- **Submodule changes** — commits that change submodule references
  may not have the submodule content available. Include
  `git submodule update --init` in the bisect script.
- **Environment differences** — the bisect script runs in your
  current environment. Commits from months ago may require different
  tool versions (Node.js, Python, etc.). Use containers or version
  managers (nvm, pyenv) in the script for reproducibility.

## Verification

- Engineering team is trained on `git bisect` and `git bisect run`.
- Regression reports include "last known good" reference points.
- CI-triggered bisect workflow exists for automated regression hunting.
- Main branch is protected with required CI checks (every commit builds).
- Bisect scripts handle build failures with exit code 125.
- Post-bisect, the root cause commit is linked in the fix PR.

## Related

- `documentation/docs/policies/worktree/git-hooks-pre-commit-frameworks.md`
- `documentation/docs/policies/worktree/git-worktree-parallel-ci-patterns.md`
- `documentation/docs/policies/testing/chaos-engineering-fault-injection.md`

## Source URLs (verified 2026-08-16)

- Git Bisect Complete Guide 2026 — https://devtoolbox.dedyn.io/blog/git-bisect-complete-guide
- How to Handle Git Bisect for Bug Finding — https://oneuptime.com/blog/post/2026-01-24-git-bisect-bug-finding/view
- Automated Git Bisect: CI-Integrated Regression Hunting — https://codeintel.xyz/blog/automated-git-bisect/
- git bisect: Find the Commit That Broke Production — https://dev.to/mdenda/git-bisect-find-the-commit-that-broke-production-in-minutes-not-days-32em
