# git-bisect-automation

**Issue:** A regression ships to production. A test that passed last week fails today. The team has 200 commits between the last good release and today. `git log` and `git blame` cannot narrow it. Manual bisection across 200 commits takes 8+ hours of "checkout, build, test, mark."
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

A bug appears in production. The team knows the last good version (`v1.42.0`) and the current bad version (`HEAD`). They need to find the exact commit that introduced the regression. Manual binary search requires running the test at every midpoint; 200 commits means ~8 iterations, each taking minutes to build and test.

## Root cause

`git bisect` is the built-in tool: it does the binary search math. You mark a known good commit and a known bad one; it checks out midpoints; you tell it good or bad; it narrows. The bottleneck is that "tell it good or bad" requires you to build and test at each midpoint. For a project where build + test takes 10 minutes, 8 iterations is 80 minutes of waiting. The fix is `git bisect run`, which automates the test step.

## The `git bisect run` contract

`git bisect run <script>` executes a script at each candidate commit. The script's exit code determines the verdict:

| Exit code | Meaning |
|---|---|
| 0 | Good commit (bug not present) |
| 1-127 (except 125) | Bad commit (bug present) |
| 125 | Skip — untestable commit |
| ≥ 128 | Abort bisect |

The script must be deterministic. If it depends on a database that has since been migrated, an external API with rate limits, or a flaky test, bisect will either crash or produce a wrong result.

## The minimal reproduction script

Write a test that catches the bug specifically, before starting bisect. A focused 30-second test beats a 10-minute full suite. Eight iterations × 10 minutes is 80 minutes; eight iterations × 30 seconds is 4 minutes.

```bash
#!/usr/bin/env bash
# scripts/bisect.sh — exit 0=good, 1=bad, 125=skip
set -euo pipefail
npm install --silent || exit 125   # can't install deps → skip
npm run build || exit 125          # build failure → skip
npm test -- --grep "regression-test"
```

```bash
git bisect start
git bisect bad HEAD
git bisect good v1.42.0
git bisect run ./scripts/bisect.sh
# ...
# 8f3a1c2d3e4f5g6h7i8j9k0l1m2n3o4p5q6r7s8t is the first bad commit
git bisect reset
```

Git does the binary search math; the script executes the same test at each midpoint. The 6-14 manual checkouts and test runs become a single command.

## The exit code 125 discipline

Some commits in the range will not compile. Without handling, the bisect aborts with a non-zero exit code. The fix is to exit 125 from the script when the commit is uncompilable, untestable, or otherwise ambiguous.

```bash
npm install --silent || exit 125
npm run build || exit 125
```

Git will treat the skipped commit as untested and narrow around it. Skipping 5-10 commits in a 200-commit range is normal; skipping 50 means the range is too messy or the script is too strict.

## The flaky test problem

If the test is non-deterministic, bisect produces garbage. A test that fails 10% of the time on a good commit will mis-identify that commit as bad, sending bisect down a wrong path.

**Solution 1 — majority voting:**

```bash
#!/usr/bin/env bash
# bisect-majority.sh — run 5 times, exit on majority
set -euo pipefail
failures=0
trials=5
for i in $(seq 1 $trials); do
  if ! npm test -- --grep "regression-test"; then
    failures=$((failures + 1))
  fi
done
if [ "$failures" -gt $(($trials / 2)) ]; then
  exit 1  # majority bad
fi
exit 0
```

**Solution 2 — Bayesian bisect (`git bayesect`):**

A third-party tool that converges correctly on flaky tests where standard bisect would mis-identify the commit. The 2-3× test count penalty is cheaper than debugging a false positive.

## The first-parent discipline

Merge commits in the range can have multiple parents. Bisect follows all parents by default, which can falsely implicate a merge commit.

Use `--first-parent` to only follow the mainline:

```bash
git bisect start --first-parent
git bisect bad HEAD
git bisect good v1.42.0
git bisect run ./scripts/bisect.sh
```

For teams using squash merges (linear history), `--first-parent` is unnecessary. For teams using merge commits, it's essential.

## The path limiting

If the bug is in a specific area, limit the search to commits that touched that path:

```bash
git bisect start HEAD v2.0.0 -- src/frontend/
```

Git will only consider commits that modified `src/frontend/`. For a known-location bug, this can cut the search from 200 commits to 30.

## The CI integration

Add a manual GitHub Actions workflow that runs the bisect automatically:

```yaml
name: Bisect Regression
on:
  workflow_dispatch:
    inputs:
      good_commit:
        description: 'Last known good commit'
        required: true
      bad_commit:
        description: 'First known bad commit'
        required: true

jobs:
  bisect:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Run automated bisect
        run: |
          git bisect start ${{ github.event.inputs.bad_commit }} ${{ github.event.inputs.good_commit }}
          git bisect run ./scripts/bisect.sh
          echo "### First bad commit" >> $GITHUB_STEP_SUMMARY
          git log -1 --oneline $(git rev-parse refs/bisect/bad) >> $GITHUB_STEP_SUMMARY
      - name: Cleanup
        run: git bisect reset
```

When main goes red, the on-call engineer kicks off the bisect workflow, and the pipeline tells them which commit broke it before standup.

## The Codex/AI-assisted bisect

For complex failures where the regression is not a single test failure but a behavioral change, the bisect script can delegate the test decision to an LLM:

```bash
#!/usr/bin/env bash
# bisect-ai.sh
set -euo pipefail
if ! npm run build 2>/dev/null; then
  exit 125
fi
codex exec \
  --approval-mode full-auto \
  -q \
  "Run the test suite for the payments module. If the tests pass, exit 0. If they fail, exit 1. Do not attempt to fix anything." \
  2>/dev/null
```

The LLM acts as a higher-level judge: it can recognize regressions that aren't captured by a single test (e.g., "the page renders but the button is in the wrong place"). Use a cheap model (`gpt-5.3-codex-spark` or similar) to keep per-step cost down.

## Verification

The tell that bisect automation is working:

- A regression on main is identified in under 30 minutes from incident to root-cause commit
- The bisect script is in the repo (e.g., `scripts/bisect.sh`)
- `exit 125` is used liberally for uncompilable intermediates
- The team uses `--first-parent` for merge-based workflows
- A CI workflow can bisect on demand

The tell it isn't:

- A regression sits for hours while someone manually checks out and tests commits
- The bisect script is not in the repo; engineers write it from scratch each time
- A flaky test mis-identifies the commit; the "fix" doesn't actually fix anything

## Gotchas

- **Write a focused test before bisect.** A 30-second test beats a 10-minute suite. Eight iterations × 10 minutes is 80 minutes of waiting.
- **Exit 125 is the most important code.** Use it for uncompilable commits, missing dependencies, broken intermediate states.
- **Flaky tests produce wrong answers.** Use majority voting or `git bayesect` if the test is non-deterministic.
- **`--first-parent` for merge-based workflows.** Without it, merge commits can be falsely implicated.
- **Limit the path when the bug is in a known area.** Cuts the search from 200 commits to 30.
- **Cleanup with `git bisect reset`.** Without it, you stay on a detached HEAD.

## Related

- `worktree/git-rerere.md` — replaying recorded conflict resolutions
- `worktree/release-please-semantic-release.md` — automated versioning
- `worktree/husky-lint-staged.md` — pre-commit quality gates

## Source URLs (verified 2026-08-10)

- https://oneuptime.com/blog/post/2026-01-24-git-bisect-bug-finding/view
- https://codex.danielvaughan.com/2026/04/25/codex-cli-automated-git-bisect-regression-hunting-root-cause-analysis/
- https://codeintel.xyz/blog/automated-git-bisect/
- https://the-practical-developer.online/posts/git-bisect-automated-regression-hunting/
- https://www.youtube.com/watch?v=hNxAUkDhzKI
