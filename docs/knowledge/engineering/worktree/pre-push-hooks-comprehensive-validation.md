# Pre-Push Hooks for Comprehensive Validation

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

The CI pipeline catches problems — broken tests, lint failures, secrets in code —
but only after a push triggers a run. Engineers wait 5–10 minutes to learn their
branch is broken. Feedback that could arrive in 30 seconds before the push arrives
in 10 minutes after it, interrupting a context switch and adding latency to the
feedback loop.

Pre-push hooks run on the developer's machine immediately before `git push` sends
anything to the remote. They are the last local gate before code becomes visible
to teammates and CI. Unlike pre-commit hooks (which run on every commit, including
intermediate WIP commits), pre-push hooks run only when the developer explicitly
decides to share their work — a natural validation boundary.

---

## Context

### How pre-push hooks work

When `git push` executes, it calls `.git/hooks/pre-push` (if it exists and is
executable) before sending any data to the remote. The hook receives two arguments:
the remote name and the remote URL. It also receives a series of lines on `stdin`
describing what is about to be pushed.

```
<local-ref> SP <local-sha1> SP <remote-ref> SP <remote-sha1> LF
```

A non-zero exit from the hook aborts the push entirely. No partial push occurs.

This STDIN stream is critical: it tells the hook exactly which commits are new
(not yet on the remote). The hook can use this to run validation only on new commits
rather than the full history.

### Pre-push vs pre-commit

| Dimension | pre-commit | pre-push |
|---|---|---|
| Runs on | Every `git commit` | Every `git push` |
| Scope | Staged changes only | All commits being pushed |
| User friction | High (fires constantly) | Low (fires on intent to share) |
| Best for | Fast formatters and syntax checks | Tests, security scans, type-checks |
| WIP commits | Interrupted constantly | Not affected |

A good hook strategy uses both: pre-commit for instant format/lint on staged files,
pre-push for the comprehensive suite that takes 30–90 seconds.

---

## Basic Pre-Push Hook

```bash
#!/usr/bin/env bash
# .git/hooks/pre-push  (or managed via Husky / Lefthook)
set -euo pipefail

echo "Running pre-push validation..."

# Read the push payload from stdin
while IFS=' ' read -r local_ref local_sha remote_ref remote_sha; do
  # Detect a branch deletion (local_sha is the zero SHA)
  if [[ "$local_sha" == "0000000000000000000000000000000000000000" ]]; then
    echo "Branch deletion push — skipping validation."
    continue
  fi

  # Detect a new branch being pushed for the first time
  if [[ "$remote_sha" == "0000000000000000000000000000000000000000" ]]; then
    # New branch: validate all commits since the branch point from main
    RANGE="$(git merge-base HEAD origin/main)..${local_sha}"
  else
    # Existing branch: validate only the new commits
    RANGE="${remote_sha}..${local_sha}"
  fi

  echo "Validating commits in range: $RANGE"

  # Validate commit messages (conventional commit format)
  git log --format="%H %s" "$RANGE" | while IFS=' ' read -r hash subject; do
    if ! echo "$subject" | grep -qE '^(feat|fix|chore|docs|style|refactor|perf|test|ci|build|revert)(\(.+\))?(!)?: .+'; then
      echo "::error:: Commit $hash has non-conventional message: '$subject'"
      exit 1
    fi
  done

done

echo "All validation passed. Proceeding with push."
exit 0
```

---

## Full Validation Suite via Husky

Manage the hook through Husky so it is version-controlled and installed automatically
for every engineer via the `prepare` lifecycle script.

### Installation

```bash
npm install --save-dev husky
npx husky init
```

### Hook file

```bash
# .husky/pre-push
#!/usr/bin/env bash
set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────
TIMEOUT_SECONDS=120   # abort the hook if it runs longer than 2 minutes
SKIP_PATTERNS=("docs/" "*.md" "documentation/")

# ── Helpers ────────────────────────────────────────────────────────────────────
log()  { echo "[pre-push] $*"; }
fail() { echo "[pre-push] FAILED: $*" >&2; exit 1; }

# ── Parse STDIN ────────────────────────────────────────────────────────────────
PUSH_LINES=()
while IFS=' ' read -r local_ref local_sha remote_ref remote_sha; do
  PUSH_LINES+=("$local_ref $local_sha $remote_ref $remote_sha")
done

# Determine the range of new commits
REMOTE_SHA="${PUSH_LINES[0]##* }"
REMOTE_SHA="${REMOTE_SHA% *}"
LOCAL_SHA=$(echo "${PUSH_LINES[0]}" | awk '{print $2}')
REMOTE_HEAD=$(echo "${PUSH_LINES[0]}" | awk '{print $4}')

if [[ "$REMOTE_HEAD" == "0000000000000000000000000000000000000000" ]]; then
  BASE=$(git merge-base HEAD origin/main 2>/dev/null || git rev-list --max-parents=0 HEAD)
else
  BASE="$REMOTE_HEAD"
fi

RANGE="${BASE}..${LOCAL_SHA}"
log "Checking commits: $RANGE"

# ── Check 1: Detect secrets with Gitleaks ─────────────────────────────────────
if command -v gitleaks &>/dev/null; then
  log "Scanning for secrets..."
  if ! gitleaks detect --log-opts="$RANGE" --no-banner -q; then
    fail "Potential secrets detected. Remove them before pushing."
  fi
  log "No secrets found."
else
  log "WARNING: gitleaks not installed. Skipping secret scan. (brew install gitleaks)"
fi

# ── Check 2: TypeScript type-check ────────────────────────────────────────────
log "Running TypeScript type-check..."
if ! timeout "$TIMEOUT_SECONDS" npx tsc --noEmit 2>&1 | tee /tmp/tsc-output.txt; then
  cat /tmp/tsc-output.txt
  fail "TypeScript errors found. Fix them before pushing."
fi
log "TypeScript: OK"

# ── Check 3: Unit tests (affected files only) ─────────────────────────────────
log "Running affected tests..."
CHANGED_FILES=$(git diff --name-only "$RANGE" | grep -E '\.(ts|tsx|js|jsx)$' || true)

if [[ -n "$CHANGED_FILES" ]]; then
  if ! timeout "$TIMEOUT_SECONDS" npx vitest run --reporter=verbose \
    $(echo "$CHANGED_FILES" | tr '\n' ' ') 2>&1; then
    fail "Test failures detected. Fix tests before pushing."
  fi
else
  log "No JS/TS files changed — skipping test run."
fi
log "Tests: OK"

# ── Check 4: No fixup! or squash! commits ─────────────────────────────────────
log "Checking for fixup/squash commits..."
FIXUPS=$(git log --format="%H %s" "$RANGE" | grep -E '^\w+ (fixup!|squash!)' || true)
if [[ -n "$FIXUPS" ]]; then
  echo "$FIXUPS"
  fail "Fixup/squash commits found. Run 'git rebase -i' to clean the history before pushing."
fi
log "No fixup commits: OK"

# ── Check 5: Merge commits in feature branch ──────────────────────────────────
TARGET_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$TARGET_BRANCH" != "main" && "$TARGET_BRANCH" != "develop" && "$TARGET_BRANCH" != "staging" ]]; then
  MERGE_COMMITS=$(git log --merges --format="%H %s" "$RANGE" || true)
  if [[ -n "$MERGE_COMMITS" ]]; then
    log "WARNING: merge commits in feature branch. Consider rebasing."
    # Warn only, do not block
  fi
fi

log "Pre-push validation complete. Pushing..."
exit 0
```

---

## Lefthook Configuration (Monorepo Alternative)

For monorepos, Lefthook's parallel runner makes the pre-push hook significantly
faster by running independent checks concurrently.

```yaml
# lefthook.yml
pre-push:
  parallel: true
  commands:
    typecheck:
      run: npx tsc --noEmit
      fail_text: "TypeScript errors. Run 'npx tsc --noEmit' to see details."

    unit-tests:
      glob: "**/*.{ts,tsx}"
      run: npx vitest run --reporter=dot
      fail_text: "Test failures detected."

    secrets:
      run: gitleaks detect --log-opts="{push_files}" --no-banner -q
      fail_text: "Potential secrets in pushed commits."
      skip:
        - merge
        - rebase

    commit-messages:
      run: |
        git log --format="%s" {push_branch}..HEAD | \
        npx commitlint --from stdin
      fail_text: "Non-conventional commit messages found."
```

```bash
# Install and enable Lefthook
npm install --save-dev @commitlint/cli @commitlint/config-conventional lefthook
npx lefthook install
```

---

## Bypassing the Hook

Some legitimate scenarios require bypassing the pre-push hook: force-pushing a
fixup after a code review, pushing during an incident when speed matters, or pushing
documentation-only changes where a 2-minute test run is wasteful.

```bash
# Skip the pre-push hook (single push)
git push --no-verify

# Skip only for this session (environment variable)
export LEFTHOOK=0  # Lefthook-specific
git push

# Skip based on branch (add to the hook script)
# At the top of the hook:
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$CURRENT_BRANCH" == docs/* ]]; then
  echo "[pre-push] Docs branch — skipping validation."
  exit 0
fi
```

`--no-verify` bypasses ALL hooks (pre-commit and pre-push). Document when this is
acceptable in your team's working agreement — typically only during incidents or for
documentation-only branches.

---

## Anti-patterns

**Running the full test suite on every push.** A 10-minute test suite in a pre-push
hook ruins the developer experience. Scope tests to affected files, or run only the
fast unit-test layer locally and leave E2E/integration tests to CI.

**Not reading STDIN.** A pre-push hook that ignores stdin and always validates the
full repo runs the same checks regardless of what is being pushed. Pushing a single
typo fix triggers a full suite run. Parse stdin and use `git diff $RANGE` to scope.

**Hard-coding branch names.** `if [[ "$BRANCH" == "main" ]]` breaks when someone
renames the default branch. Use `git symbolic-ref refs/remotes/origin/HEAD` to
discover the default branch dynamically.

**Blocking on slow network-dependent checks.** Secret scanning that phones home,
or SCA checks that download databases, add unpredictable latency. Prefer offline
tools (gitleaks with a local config) and leave network-dependent checks to CI.

**No bypass mechanism.** Hooks without a sanctioned bypass path cause engineers to
delete the hook entirely. Provide `--no-verify` as the documented escape hatch and
log usage in CI to detect abuse patterns.

---

## Gotchas

- Hooks installed in `.git/hooks/` are not tracked in the repository. Every clone
  must re-install them. Use Husky's `prepare` lifecycle or Lefthook's `install`
  command in the repository's `postinstall` script to automate this.

- On branch pushes, `remote_sha` for a new branch is the zero SHA
  (`0000000000000000000000000000000000000000`). Failing to handle this case causes
  the hook to try `git log 000..HEAD`, which may fail or produce unexpected output.

- `git push --force` and `git push --force-with-lease` both trigger the pre-push
  hook. The hook cannot distinguish a normal push from a force-push; check for
  force-push by examining the command line via `/proc/$PPID/cmdline` (Linux) if you
  need different behavior.

- Husky v9+ changed the hook installation path from `.husky/_/` to `.husky/`. If
  upgrading from v8, update the hook files accordingly.

- Lefthook's `{push_files}` template variable resolves to the list of files in the
  push range, but it may be empty for tag pushes or empty-commit pushes. Guard with
  a null check.

---

## Verification

```bash
# Confirm the hook is installed and executable
ls -la .git/hooks/pre-push
stat -c "%a" .git/hooks/pre-push  # should be 755

# Dry-run: trigger the hook without actually pushing
# (simulate what git would pipe to the hook)
echo "refs/heads/feature/test $(git rev-parse HEAD) refs/heads/feature/test 0000000000000000000000000000000000000000" \
  | .git/hooks/pre-push origin git@github.com:org/repo.git

# Verify Lefthook is active
npx lefthook run pre-push

# Verify Husky is configured
cat package.json | jq '.scripts.prepare'
# should print: "husky"

# Confirm --no-verify bypass works (useful to document)
git push --dry-run --no-verify
```

---

## Related

- `pre-commit-hooks-comparison-2026.md` — pre-commit hook frameworks (Husky,
  Lefthook, pre-commit) and their tradeoffs
- `git-hooks-husky-lint-staged-commitlint.md` — Husky + lint-staged setup for
  staged-file validation
- `git-hooks-lefthook-monorepo.md` — Lefthook configuration for monorepos
- `secret-scanning-2026.md` — gitleaks and server-side secret scanning complement

---

## Sources

- `githooks` man page: https://git-scm.com/docs/githooks#_pre_push
- Gitleaks: https://github.com/gitleaks/gitleaks
- Husky documentation: https://typicode.github.io/husky/
- Lefthook documentation: https://github.com/evilmartians/lefthook
- Vitest CLI reference: https://vitest.dev/guide/cli
