# git-bisect-run-2026

**Issue:** git bisect run — automated regression finding
**Date:** 2026-08-09
**Status:** documented

## Symptom
Production bug. 200 commits since. Bisecting by hand
takes 4 hours. The on-call is paged. You wish you
had automated bisect.

## Root cause
**Manual bisect is slow.** Use `git bisect run`.

**Source:** MIT bisect + CodeIntel 2026.

## The "bisect run" concept

`git bisect run`:
- **Algorithm:** Binary search O(log n)
- **Test:** Script exits 0 (good) / 1 (bad) / 125 (skip)
- **Time:** 30 min manual → 1 command
- **Use:** Find first bad commit

The bisect is the search.

## The "exit codes" pattern

For codes:
- **0:** Good (bug absent)
- **1-127 (except 125):** Bad (bug present)
- **125:** Skip (untestable)
- **≥128:** Abort

The code is the verdict.

## The "regression test" pattern

For test:
```bash
#!/usr/bin/env bash
# bisect-test.sh
set -euo pipefail
npm ci --silent || exit 125
npm test -- --grep "regression-test"
```

The test is exit-coded.

## The "start" pattern

For start:
```bash
git bisect start HEAD v2.0.0
git bisect run ./bisect-test.sh
```

The start is one command.

## The "result" pattern

For result:
```
abc123def is the first bad commit
commit <commit-sha> (HEAD)
Author: ...
Date: ...

    Add payments retry logic
```

The result is the SHA.

## The "skip pattern" pattern

For untestable:
```bash
#!/usr/bin/env bash
set -euo pipefail
npm ci --silent || exit 125
npm run build || exit 125
npm test -- --grep "regression-test"
```

The skip is graceful.

## The "majority voting" pattern

For flaky:
```bash
#!/usr/bin/env bash
set -euo pipefail
failures=0
trials=5
for i in $(seq 1 $trials); do
  if ! npm test -- --grep "regression"; then
    failures=$((failures + 1))
  fi
done
if [ "$failures" -gt $((trials / 2)) ]; then
  exit 1
fi
exit 0
```

The vote is per test.

## The "AI-powered bisect" pattern

For LLM:
```bash
#!/usr/bin/env bash
# bisect-test.sh with Codex CLI
set -euo pipefail
if ! npm run build 2>/dev/null; then
  exit 125
fi
codex exec \
  --approval-mode full-auto \
  -q \
  "Run 'npm test -- --testPathPattern=payments'.
  Exit 0 if pass, 1 if fail. Don't fix." \
  2>/dev/null
```

The AI is the test.

## The "AI analysis" pattern

For root cause:
```bash
# After bisect finds commit
FIRST_BAD=$(git bisect view --format="%H" | head -1)
codex exec \
  "Analyze diff of $FIRST_BAD vs parent.
  Explain why this broke the payments test.
  Suggest minimal fix."
```

The AI is the analyzer.

## The "pathspec" pattern

For narrow:
```bash
# Only consider commits that touched src/frontend/
git bisect start HEAD v2.0.0 -- src/frontend/
```

The scope is narrow.

## The "first-parent" pattern

For clean:
```bash
# Skip merge commits
git bisect start --first-parent HEAD v2.0.0
```

The history is clean.

## The "log everything" pattern

For audit:
```bash
git bisect run ./bisect-test.sh 2>&1 | tee bisect.log
```

The log is per run.

## The "CI integration" pattern

For GitHub Actions:
```yaml
# .github/workflows/auto-bisect.yml
name: Auto Bisect
on: workflow_dispatch
jobs:
  bisect:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Required!
      - run: |
          git bisect start ${{ inputs.bad }} ${{ inputs.good }}
          git bisect run ./scripts/bisect-test.sh
          echo "### First bad" >> $GITHUB_STEP_SUMMARY
          git log -1 --oneline $(git rev-parse refs/bisect/bad) \
            >> $GITHUB_STEP_SUMMARY
      - run: git bisect reset
```

The CI is integrated.

## The "fetch-depth" pattern

For CI:
- **Required:** `fetch-depth: 0`
- **Why:** Shallow = no history
- **Effect:** Bisect fails silently

The fetch is full.

## The "AI + bisect" pattern

For modern:
- **Tool:** Codex CLI, Claude Code
- **Test:** AI evaluates
- **Analyze:** AI explains
- **Speed:** 1 command

The AI is the tool.

## The "Bayesian bisect" pattern

For flaky:
```bash
git bayesect start HEAD v2.0.0
git bayesect run ./test.sh
# Multiple runs per commit
```

The Bayes handles uncertainty.

## The "small commits" pattern

For bisect-friendly:
- **Small:** Per commit
- **Single:** One logical change
- **Tested:** CI green
- **Result:** Bisect works

The commit is small.

## The "no test" anti-pattern

For no test:
- **Issue:** Bisect without oracle
- **Fix:** Write test first

The test is required.

## The "shallow clone" anti-pattern

For shallow:
- **Issue:** Bisect silently fails
- **Fix:** `fetch-depth: 0`

The clone is full.

## The "manual bisect" anti-pattern

For manual:
- **Issue:** 4 hours
- **Fix:** `bisect run` + script

The run is automated.

## The "no skip" anti-pattern

For no skip:
- **Issue:** Stuck on broken
- **Fix:** `exit 125` for untestable

The skip is graceful.

## The "flaky without voting" anti-pattern

For flaky:
- **Issue:** False positive
- **Fix:** Majority voting

The vote is per commit.

## The "no log" anti-pattern

For no log:
- **Issue:** Can't review
- **Fix:** Tee to file

The log is required.

## The "bisect in CI" pattern

For CI:
- **Trigger:** Manual (workflow_dispatch)
- **Inputs:** good + bad
- **Result:** PR comment
- **Cleanup:** `git bisect reset`

The CI is gated.

## The "what to look for" pattern

For signals:
- **Manual hunts:** Automate
- **Monthly rollbacks:** Auto-bisect
- **Staging-only fails:** Auto-bisect
- **Long PRs:** Conflict resolution hunt

The signal is per incident.

## The "merge bisect" pattern

For merge:
- **Issue:** Merge commit breaks
- **Fix:** Test on merge, not on each side
- **Or:** Test first parent only

The merge is per need.

## The "post-bisect analysis" pattern

For after:
```bash
# What changed
git show $FIRST_BAD

# Who
git blame $FIRST_BAD -- file.ts

# When
git log --since=$FIRST_BAD
```

The analysis is per commit.

## The "fix forward" pattern

For after:
1. **Revert:** On main
2. **Cherry-pick:** Release branches
3. **Fix forward:** On feature
4. **PR:** Corrected
5. **Supersedes:** Revert

The fix is forward.

## The "bisect script template" pattern

For template:
```bash
#!/usr/bin/env bash
# scripts/bisect-template.sh
set -euo pipefail
# Install
if ! npm ci --silent 2>/dev/null; then
  exit 125
fi
# Build
if ! npm run build 2>/dev/null; then
  exit 125
fi
# Test (specific)
npm test -- --grep "specific-regression"
```

The template is reusable.

## The "bisect checklist" pattern

For checklist:
- [ ] Test written first
- [ ] Script: exit 0/1/125
- [ ] Skips for unbuildable
- [ ] Voting for flaky
- [ ] Pathspec if narrow
- [ ] First-parent for clean
- [ ] Log captured
- [ ] Cleanup: bisect reset
- [ ] fetch-depth: 0 in CI
- [ ] AI analysis after

The checklist is 10.

## Verification
- **Test:** Bisect finds
- **Test:** No false positive
- **Test:** Log clear
- **Test:** Reset clean
- **Audit:** Quarterly

## Gotchas
- **The "no test" anti-pattern.** Write first.
- **The "shallow clone" anti-pattern.** fetch-depth: 0.
- **The "flaky" anti-pattern.** Vote.

## Related
- `worktree/cherry-pick-revert-bisect.md`
- `worktree/rebase-vs-merge-detail.md`
- `worktree/git-hooks-2026.md`
- `patterns/test-pyramid-2026.md`
- `deploy/canary-deployments.md`
- CodeIntel: https://codeintel.xyz/blog/automated-git-bisect/
- Codex: https://codex.danielvaughan.com/2026/04/25/codex-cli-automated-git-bisect-regression-hunting-root-cause-analysis/
- MIT bisect: https://web.mit.edu/git/www/git-bisect-lk2009.html
