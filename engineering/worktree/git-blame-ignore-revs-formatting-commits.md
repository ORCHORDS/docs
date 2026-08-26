# git blame --ignore-revs Formatting Commits

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your team adopted Prettier or dprint across the entire Workers monorepo in a single mass-formatting commit. Now `git blame` on any file shows that commit as the author of 80% of lines. Tracing the actual logic author for a bug requires manually stepping back through history with `git log -p` on every suspicious line. GitHub's blame view is similarly polluted. You want `git blame` to skip the formatting commit and show the true author of each line's content.

## Context

Git 2.23 introduced `--ignore-rev` (single revision) and `--ignore-revs-file` (a file listing multiple revisions) for `git blame`. When a commit is ignored, Git reassigns each line that the ignored commit last touched to the nearest ancestor commit that previously introduced that line. The effect is as if the formatting commit never existed, without rewriting history.

The `.git-blame-ignore-revs` file is the community convention for storing the list of commits to ignore. GitHub's web blame view honours this file automatically if it is committed to the repository root. VS Code's GitLens and most other blame tools support it via configuration.

---

## Creating the .git-blame-ignore-revs File

After running a mass-formatting pass, record the commit SHA:

```bash
# Find the formatting commit
git log --oneline --all | grep -i "format\|prettier\|dprint\|lint:fix"
# a3f2c91 chore: apply Prettier across all Workers packages
# 9e8b104 chore: enforce dprint on monorepo root

# Create or append to the file
cat >> .git-blame-ignore-revs << 'EOF'
# Prettier mass-format 2026-01-15
a3f2c91e4d8b2a7f1c9e3d5a6b8c0f2e4d6a8b0f

# dprint enforcement 2026-03-02
9e8b104a3f5c7e2d4b6a8c0e2f4d6a8b0c2e4f6a
EOF
```

Commit the file:

```bash
git add .git-blame-ignore-revs
git commit -m "chore: add blame ignore revs for formatting commits"
```

---

## Using the File in git blame

Point `git blame` at the file explicitly:

```bash
git blame --ignore-revs-file .git-blame-ignore-revs src/handlers/roles.ts
```

Configure git to use the file automatically for all blame invocations in this repository:

```bash
git config blame.ignoreRevsFile .git-blame-ignore-revs
```

Or add it to the project's `.gitconfig` so every contributor gets it:

```ini
# .gitconfig  (commit to repo root, then: git config --local include.path ../.gitconfig)
[blame]
  ignoreRevsFile = .git-blame-ignore-revs
```

After configuration, `git blame src/handlers/roles.ts` skips formatting commits automatically.

---

## Annotating the File with Context

The `.git-blame-ignore-revs` file supports comments (lines starting with `#`) and blank lines:

```
# =============================================================
# git blame ignore-revs
# Add full 40-char SHAs of bulk-change commits that should not
# appear as the "author" of lines they merely reformatted.
# =============================================================

# 2026-01-15: Prettier v3 migration across all packages
# PR: https://github.com/org/repo/pull/412
a3f2c91e4d8b2a7f1c9e3d5a6b8c0f2e4d6a8b0f

# 2026-03-02: dprint enforcement + trailing-newline fix
# PR: https://github.com/org/repo/pull/589
9e8b104a3f5c7e2d4b6a8c0e2f4d6a8b0c2e4f6a

# 2026-06-10: ESLint auto-fix on import ordering
# PR: https://github.com/org/repo/pull/731
b7d3e52f1a4c6e8d0b2f4a6c8e0b2d4f6a8c0e2f
```

Short SHAs (7 chars) work but full 40-character SHAs are preferred to avoid ambiguity in large repositories.

---

## Configuring GitHub Web Blame

GitHub automatically reads `.git-blame-ignore-revs` from the repository root on the default branch. No additional configuration is required. Once the file is merged into `main`, the GitHub blame view skips those commits when you click "Blame" on any file.

To verify GitHub is respecting the file: open any file modified by the formatting commit in the GitHub UI, click "Blame", and confirm the formatting commit SHA does not appear in the gutter.

---

## Workers Monorepo Example: Per-Package Formatting Commits

In a monorepo where different packages were formatted at different times:

```
# .git-blame-ignore-revs

# packages/api-gateway: Prettier applied 2026-01-15
a3f2c91e4d8b2a7f1c9e3d5a6b8c0f2e4d6a8b0f

# packages/auth-worker: dprint applied 2026-02-20
c5e7a92b3d1f4g8h9i0j1k2l3m4n5o6p7q8r9s0t

# packages/queue-consumer: ESLint --fix 2026-04-05
d8f1b3e5a7c9e2f4b6d8f0a2b4c6d8e0f2a4b6c8
```

All blame invocations across the monorepo skip the listed commits regardless of which package file is being blamed.

---

## Integrating with VS Code GitLens

GitLens uses `git blame` under the hood and inherits the `blame.ignoreRevsFile` config automatically when the repo-level config is set. If GitLens is reading the wrong commit for a line:

1. Ensure `git config blame.ignoreRevsFile` returns `.git-blame-ignore-revs`.
2. Reload the VS Code window (`Ctrl+Shift+P` > "Reload Window").
3. Open a file affected by the formatting commit and hover a line — GitLens should now show the pre-format author.

For the `include.path` approach, VS Code must be opened in the repository root so git picks up the local config:

```bash
code /path/to/project
```

---

## Anti-patterns

- **Using short SHAs in `.git-blame-ignore-revs`**: short SHAs can become ambiguous as the repository grows. Always use the full 40-character SHA output from `git log --format="%H"`.
- **Adding merge commits to the ignore file**: merge commits rarely author lines directly. Adding them produces unexpected line attribution jumps. Only add commits that actually modified file content (formatting, auto-fix, import sort).
- **Ignoring feature commits to hide authorship**: the ignore-revs mechanism exists for reformatting and tooling commits only. Using it to obscure functional changes corrupts the audit trail and violates the purpose of `git blame`.
- **Forgetting to commit `.git-blame-ignore-revs`**: the file only takes effect for other contributors and GitHub when it is committed. Keeping it local via `git config blame.ignoreRevsFile /abs/path` helps only you.

---

## Gotchas

- `git blame --ignore-revs-file` requires git 2.23 or later. Check with `git --version`. Most CI runners and macOS Homebrew installations are current, but verify if your team has locked git versions.
- If a commit SHA in `.git-blame-ignore-revs` does not exist in the local repository (e.g. was not fetched), git silently skips it rather than erroring. Always verify with `git cat-file -t <sha>` returning `commit`.
- Lines introduced for the first time by a formatting commit (e.g. the formatter added a blank line that did not exist before) are attributed to the formatting commit itself even with `--ignore-revs`. Only pre-existing line content gets reassigned.
- The `blame.markIgnoredLines` and `blame.markUnblamableLines` config options (git 2.38+) add `?` or `*` markers in the blame output for lines that were either ignored or could not be attributed to a predecessor.

---

## Verification

```bash
# Confirm the formatting commit SHA is correct
git log --format="%H %s" | grep -i "prettier\|dprint\|format"

# Test blame without the ignore file (shows formatting commit)
git blame src/handlers/roles.ts | head -20

# Test blame with the ignore file (shows true author)
git blame --ignore-revs-file .git-blame-ignore-revs src/handlers/roles.ts | head -20

# After setting git config, confirm it is respected globally for this repo
git config blame.ignoreRevsFile
# .git-blame-ignore-revs

git blame src/handlers/roles.ts | head -20
# Should no longer show the formatting commit SHA
```

---

## Related

- `git-blame-code-archaeology.md`
- `conventional-commits-2026.md`
- `git-hooks-pre-commit-frameworks.md`
- `pre-commit-hooks-comparison-2026.md`
- `husky-lint-staged.md`

---

## Sources

- git-scm.com/docs/git-blame
- docs.github.com/en/repositories/working-with-files/using-files/viewing-a-file#ignore-commits-in-the-blame-view
- git-scm.com/docs/git-config — blame.ignoreRevsFile
- prettier.io/docs/en/install.html
