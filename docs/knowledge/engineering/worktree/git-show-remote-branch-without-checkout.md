# git show Remote Branch Content Without Checkout

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A colleague opens a PR and asks you to review a specific file — say, the `wrangler.toml` or a D1 migration — before you are ready to check out their branch. Your current worktree has unsaved work. You want to read, diff, or copy the file content from their branch without switching branches, creating a worktree, or stashing anything. You also want to inspect what a remote branch's `package.json` declares as a deploy script before pulling it.

## Context

`git show` is a porcelain command that prints the content of any git object: commits, trees, blobs, and tags. Combined with a tree-ish reference such as `origin/feature/new-migration:path/to/file.sql`, it resolves the remote-tracking ref without touching the working tree. No checkout, no stash, no worktree.

Remote-tracking refs (`origin/branch-name`) are updated by `git fetch`. They represent the last-fetched state of the remote; if you need the very latest, run `git fetch origin branch-name` first. After that `git show origin/branch-name:path` reads directly from the local object store.

---

## Reading a Single File from a Remote Branch

```bash
# Fetch the latest state of the branch
git fetch origin feature/add-user-roles

# Show the wrangler.toml from that branch
git show origin/feature/add-user-roles:wrangler.toml
```

For a D1 migration file:

```bash
git show origin/feature/add-user-roles:migrations/0004_add_user_roles.sql
```

Pipe into `less` for long files:

```bash
git show origin/feature/add-user-roles:src/index.ts | less
```

---

## Diffing a File Between Main and a Remote Branch

```bash
# Diff wrangler.toml between main and the feature branch
git diff origin/main origin/feature/add-user-roles -- wrangler.toml
```

Diff a TypeScript file with word-level diff to spot small changes:

```bash
git diff --word-diff origin/main origin/feature/add-user-roles -- src/handlers/roles.ts
```

Compare the same file across three points:

```bash
# What exists on main
git show origin/main:src/handlers/roles.ts

# What the branch proposes
git show origin/feature/add-user-roles:src/handlers/roles.ts

# What you currently have locally
cat src/handlers/roles.ts
```

---

## Inspecting Wrangler Configuration Before Pulling

When a colleague's PR changes `wrangler.toml` bindings you want to review before merging:

```bash
git fetch origin feature/add-kv-binding
git show origin/feature/add-kv-binding:wrangler.toml
```

Sample output reviewed without checkout:

```toml
name = "my-api"
compatibility_date = "2026-06-01"

[[kv_namespaces]]
binding = "SESSIONS"
id = "abc123def456"

[env.staging.kv_namespaces]
binding = "SESSIONS"
id = "staging-abc123"
```

If the production `id` looks wrong you can comment on the PR immediately without ever switching branches.

---

## Listing Files Changed in a Remote Branch

```bash
# List files changed between main and the remote feature branch
git diff --name-only origin/main...origin/feature/add-user-roles
```

Show only changed file names with their change type:

```bash
git diff --name-status origin/main...origin/feature/add-user-roles
# M  src/handlers/roles.ts
# A  migrations/0004_add_user_roles.sql
# M  wrangler.toml
```

The three-dot `...` form computes the diff from the merge-base, which matches what a PR shows.

---

## Extracting a File from a Remote Branch to Disk

Sometimes you want a copy of a remote file without checking out the branch. Write it to a temp location:

```bash
git show origin/feature/add-user-roles:migrations/0004_add_user_roles.sql \
  > /tmp/migration-preview-0004.sql

# Review it
cat /tmp/migration-preview-0004.sql

# Validate it with sqlite3 against a local copy of the DB
sqlite3 /tmp/test.db < /tmp/migration-preview-0004.sql
```

For a Workers TypeScript source file you want to test locally without switching:

```bash
git show origin/feature/add-user-roles:src/lib/auth.ts > /tmp/auth-preview.ts
npx tsc --noEmit /tmp/auth-preview.ts 2>&1 | head -20
```

---

## Scripting Multi-file Inspection of a Remote Branch

Inspect all changed `.sql` files in a branch:

```bash
#!/usr/bin/env bash
# scripts/preview-migrations.sh
BRANCH="${1:?Usage: $0 <branch>}"
git fetch origin "$BRANCH"

git diff --name-only origin/main..."origin/$BRANCH" -- 'migrations/*.sql' \
| while read -r FILE; do
  echo "=== $FILE ==="
  git show "origin/$BRANCH:$FILE"
  echo ""
done
```

```bash
bash scripts/preview-migrations.sh feature/add-user-roles
# === migrations/0004_add_user_roles.sql ===
# CREATE TABLE user_roles ( ...
```

Inspect the `wrangler.toml` bindings diff across all Workers packages in a monorepo:

```bash
#!/usr/bin/env bash
BRANCH="${1:?branch required}"
git fetch origin "$BRANCH"

find . -name "wrangler.toml" -not -path "*/.wrangler/*" \
| while read -r CFG; do
  REL="${CFG#./}"
  if ! git diff --quiet "origin/main" "origin/$BRANCH" -- "$REL" 2>/dev/null; then
    echo "--- $REL changed ---"
    git diff origin/main "origin/$BRANCH" -- "$REL"
  fi
done
```

---

## Anti-patterns

- **Checking out the branch to read a single file**: a full checkout modifies hundreds of files, triggers TypeScript compilation, invalidates build caches, and blocks your active work. `git show` reads the object from the local store in milliseconds.
- **Using `git stash` just to peek at a file**: stash is for saving incomplete work, not for context-switching to read a colleague's file. Use `git show` and keep stash for genuine work-in-progress situations.
- **Reading from `origin/branch` without fetching**: the remote-tracking ref reflects the last-fetched state. If the colleague pushed commits after your last fetch you will read stale content. Always `git fetch origin <branch>` before using `git show origin/<branch>:path`.
- **Copying files from remote branches manually via GitHub UI**: the web UI truncates large files and shows no git context. `git show` delivers the exact blob the CI pipeline will see.

---

## Gotchas

- The colon separator in `ref:path` is mandatory. `git show origin/branch path/to/file` (with a space) shows the commit object and the file separately rather than the file at that ref.
- Paths in `git show ref:path` are always relative to the repository root, not the current directory. `git show origin/main:src/index.ts` works regardless of where you are inside the repo.
- Binary files (compiled assets, images) are shown as raw bytes. Pipe to `xxd` or redirect to a file instead of printing to the terminal.
- `git show` on a directory path outputs a tree listing, not file contents. To show a directory's tree: `git ls-tree origin/main src/handlers/`.

---

## Verification

```bash
# Fetch and inspect
git fetch origin feature/add-user-roles
git show origin/feature/add-user-roles:wrangler.toml

# Confirm no files were changed in your working tree
git status
# On branch main
# nothing to commit, working tree clean

# List what changed between main and the remote branch
git diff --name-status origin/main...origin/feature/add-user-roles
```

---

## Related

- `git-worktree-parallel-d1-schema-migration.md`
- `git-range-diff-review-after-rebase.md`
- `git-stash-2026.md`
- `code-review-checklist.md`
- `pr-review-process-2026.md`

---

## Sources

- git-scm.com/docs/git-show
- git-scm.com/docs/git-diff
- git-scm.com/docs/git-ls-tree
- git-scm.com/docs/gitrevisions
