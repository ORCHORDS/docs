# Git Hooks in Worktrees: Isolation and Per-Worktree Overrides

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You add a second git worktree and notice:

- `pre-commit` hooks from the main repo fire in the feature worktree (expected but sometimes surprising)
- You want a stricter lint check in the main worktree but a faster (or no) check in an experimental worktree
- A monorepo's `commit-msg` hook references a path that only exists in the primary worktree
- You use lefthook or husky and wonder whether their config is respected per-worktree

---

## Context

All git worktrees share a single `.git` directory (or, for secondary worktrees, `.git/worktrees/<name>`). The hooks directory at `.git/hooks/` is **shared** across every worktree by default. Only one hooks directory exists regardless of how many worktrees you have.

Git 2.9 introduced `core.hooksPath` — a config key that overrides the hooks directory with any absolute or relative path. When set in a worktree-local config, it applies only to that worktree, giving you per-worktree hook isolation without touching the shared `.git/hooks/`.

---

## Section 1: Understanding the Default (Shared) Hooks Behaviour

```bash
# Show the hooks directory for the current worktree
git rev-parse --git-path hooks
# Primary worktree:    /path/to/project
# Secondary worktree:  /path/to/project  ← same path!

# List active hooks
ls /path/to/project | grep -v '\.sample$'
# pre-commit
# commit-msg
# prepare-commit-msg
```

This means any hook installed by `husky install` or `lefthook install` in the primary worktree fires for commits made in secondary worktrees too. Usually this is the desired behaviour (consistent quality gates). The issues arise when:

- A hook does `cd "$(git rev-parse --show-toplevel)"` and expects to land in the primary worktree — it will land in whichever worktree the commit is in.
- A hook references `./node_modules/.bin/eslint` and the secondary worktree uses a symlinked `node_modules` pointing elsewhere (see the symlink article).

---

## Section 2: Per-Worktree Hook Override with `core.hooksPath`

```bash
# Inside the secondary worktree
cd /path/to/project

# Create a worktree-local hooks directory
mkdir -p .git-hooks

# Configure this worktree to use its own hooks directory
git config --worktree core.hooksPath .git-hooks

# Verify
git config --show-scope core.hooksPath
# worktree    .git-hooks

# Now hooks in .git-hooks take effect for this worktree
# The shared .git/hooks/ hooks are ignored
```

> **Note**: `--worktree` scope requires `extensions.worktreeConfig = true` in `.git/config`:

```bash
# Enable per-worktree config (run once per repo)
git config extensions.worktreeConfig true

# Confirm
git config --local extensions.worktreeConfig
# true
```

---

## Section 3: Writing Worktree-Aware Hook Scripts

Rather than completely different hooks per worktree, the common pattern is a single hook script that detects which worktree it is running in and adjusts behaviour:

```bash
#!/usr/bin/env bash
# .git/hooks/pre-commit
# Shared pre-commit hook that adapts per worktree
set -euo pipefail

WORKTREE_ROOT="$(git rev-parse --show-toplevel)"
BRANCH="$(git symbolic-ref --short HEAD 2>/dev/null || echo 'HEAD')"

echo "[pre-commit] worktree: $WORKTREE_ROOT"
echo "[pre-commit] branch:   $BRANCH"

# Skip heavy checks on branches prefixed with 'wip/' or 'exp/'
if [[ "$BRANCH" == wip/* ]] || [[ "$BRANCH" == exp/* ]]; then
  echo "[pre-commit] WIP/experimental branch — skipping lint"
  exit 0
fi

# Run lint from the worktree root (handles symlinked node_modules)
cd "$WORKTREE_ROOT"
"$WORKTREE_ROOT/node_modules/.bin/eslint" \
  --max-warnings=0 \
  $(git diff --cached --name-only --diff-filter=ACMR | grep -E '\.(ts|tsx|js|jsx)$' || true)

echo "[pre-commit] lint passed"
```

```bash
chmod +x .git/hooks/pre-commit
```

---

## Section 4: Lefthook Worktree-Aware Configuration

Lefthook reads `lefthook.yml` from the **current worktree root** (the directory returned by `git rev-parse --show-toplevel`). This means you can have different `lefthook.yml` files on different branches.

```yaml
# lefthook.yml on main branch — strict checks
pre-commit:
  parallel: true
  commands:
    lint:
      glob: "*.{ts,tsx}"
      run: npx eslint --max-warnings=0 {staged_files}
    typecheck:
      run: npx tsc --noEmit
    test:
      run: npx vitest run --changed

commit-msg:
  commands:
    conventional:
      run: npx commitlint --edit {1}
```

```yaml
# lefthook.yml on feature/experimental branch — lighter checks
pre-commit:
  parallel: true
  commands:
    lint:
      glob: "*.{ts,tsx}"
      run: npx eslint --max-warnings=50 {staged_files}
    # typecheck and test omitted for fast iteration

commit-msg:
  skip: true  # no conventional commit enforcement on experimental branch
```

```bash
# Install lefthook in the primary worktree (installs to .git/hooks/)
cd /path/to/project
npx lefthook install

# In the secondary worktree, lefthook reads its own lefthook.yml
cd /path/to/project
git log --oneline -1  # confirm we're on the feature branch
npx lefthook run pre-commit  # uses the feature branch's lefthook.yml
```

---

## Section 5: Husky in Worktrees

Husky v9+ respects `core.hooksPath`. After `npx husky init`, hooks are written to `.husky/`. Set the path once globally for the repo:

```bash
git config core.hooksPath .husky
```

Husky hooks then fire for all worktrees (because the config is repo-local, not worktree-local). To skip husky in a specific worktree:

```bash
# In the experimental worktree, override hooksPath to an empty dir
cd /path/to/project
git config extensions.worktreeConfig true
mkdir -p .git-hooks-empty
git config --worktree core.hooksPath .git-hooks-empty
# Now no hooks fire in this worktree
```

Alternatively, set `HUSKY=0` in the worktree's `.vscode/settings.json` terminal env or `.envrc`:

```bash
# .envrc in the experimental worktree (direnv)
export HUSKY=0
```

---

## Anti-patterns

- **Hard-coding the primary worktree path in a hook** (e.g., `cd /path/to/project && npm test`) — use `git rev-parse --show-toplevel` instead so the hook works from any worktree.
- **Running `npx husky install` in a secondary worktree** — Husky installs hooks into `.git/hooks/` which is shared; running it again from a secondary worktree rewrites the hooks, potentially with the wrong `$PATH` or env.
- **Committing `.git-hooks/` into the repo** — these files will be checked out in all worktrees but only used where `core.hooksPath` points to them; confusing unless clearly documented.
- **Disabling all hooks globally** (`git config core.hooksPath /dev/null`) to work around a noisy hook — fix the hook instead.

---

## Gotchas

- `git config --worktree` writes to `.git/worktrees/<name>/config.worktree` for secondary worktrees, and to `.git/config.worktree` for the primary. These files are not shared.
- `extensions.worktreeConfig = true` must be set before `--worktree`-scoped config writes work. Without it, Git silently ignores the scope flag and writes to the local (repo-wide) config instead.
- Hooks written as absolute paths (e.g., `#!/usr/bin/env node /path/to/project) break in secondary worktrees if the hook file does not exist at that path.
- `git worktree add` does not copy or link existing hooks into the new worktree's directory; you must configure `core.hooksPath` explicitly if you want worktree-specific hooks.
- When using Docker or Nix shells where the PATH differs between environments, hooks that call local binaries via `npx` are more portable than direct paths like `./node_modules/.bin/cmd`.

---

## Verification

```bash
# Confirm shared hooks path for primary worktree
cd /path/to/project
git rev-parse --git-path hooks
# /path/to/project

# Confirm per-worktree override for secondary
cd /path/to/project
git config --show-scope core.hooksPath
# worktree    .git-hooks
git rev-parse --git-path hooks
# Should now report the .git-hooks path

# Trigger a commit to test the hook fires (and uses the right config)
git commit --allow-empty -m "test: verify hook fires"
# Should show [pre-commit] worktree: /path/to/project

# Confirm worktreeConfig extension is enabled
git config --local extensions.worktreeConfig
# true
```

---

## Related

- `documentation/docs/policies/worktree/git-worktree-feature-flag-parallel-dev.md`
- `documentation/docs/policies/worktree/git-worktree-vscode-multi-root-workspace.md`
- `documentation/docs/policies/worktree/git-worktree-sparse-checkout-large-monorepo.md`

---

## Sources

- https://git-scm.com/docs/git-config#Documentation/git-config.txt-corehooksPath
- https://git-scm.com/docs/git-worktree
- https://typicode.github.io/husky/
- https://lefthook.dev/configuration/
- https://git-scm.com/docs/git-config#Documentation/git-config.txt-extensionsworktreeConfig
