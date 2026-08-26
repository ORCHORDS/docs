# Git Worktree for Code Review: Parallel PR Checkout

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You are deep in feature work on `feature/auth-refactor` and a colleague opens a PR that needs review. Switching branches destroys your editor state, stashes are fragile, and rebuilding node_modules or compilation artifacts wastes minutes. `git worktree add` solves this by checking out the PR branch into a separate directory without touching your current working tree.

## Context

- Git 2.15+
- Any language project (Node.js, Go, Python, Rust)
- GitHub / GitLab PR-based review workflow
- Shell: bash or zsh

---

## Section 1: Add a Worktree for the PR Branch

```bash
# Fetch all remote branches first
git fetch origin

# Add a worktree for the PR branch into a sibling directory
# Convention: use ../repo-name--branch-name to keep it obvious
git worktree add ../myrepo--pr-456 origin/feature/teammate-widget

# List active worktrees
git worktree list
# /path/to/project              a1b2c3d [feature/auth-refactor]
# /path/to/project     f9e8d7c [feature/teammate-widget]
```

The new directory is a full working tree: you can run tests, install deps, and open a second editor instance pointing at it — your original tree is completely undisturbed.

```bash
# Open a second VSCode window on the PR worktree
code ../myrepo--pr-456

# Or open neovim in the PR worktree from a split terminal
pushd ../myrepo--pr-456
nvim .
popd
```

---

## Section 2: Diffing Across Worktrees

```bash
# Compare a specific file between your working branch and the PR branch
diff \
  <(cat /path/to/project) \
  <(cat /path/to/project)

# Use git diff with explicit tree references (no worktree switch needed)
git diff feature/auth-refactor..feature/teammate-widget -- src/widgets/

# Delta / difftastic side-by-side if installed
delta \
  /path/to/project \
  /path/to/project

# Run both test suites and compare output
pushd /path/to/project && npm test 2>&1 | tee /tmp/main-tests.txt; popd
pushd /path/to/project && npm test 2>&1 | tee /tmp/pr-tests.txt; popd
diff /tmp/main-tests.txt /tmp/pr-tests.txt
```

---

## Section 3: Reviewing, Commenting, and Cleaning Up

```bash
# Install dependencies in the PR worktree independently
pushd ../myrepo--pr-456
npm ci          # or: pip install -r requirements.txt / go mod download
npm run build
npm test
popd

# Leave a review comment via GitHub CLI without leaving your terminal
gh pr review 456 \
  --comment \
  --body "Tested locally in a worktree — build passes, tests green."

# Approve the PR
gh pr review 456 --approve

# Clean up the worktree when done
git worktree remove ../myrepo--pr-456
# If the branch had uncommitted changes, add --force
# git worktree remove --force ../myrepo--pr-456

# Prune any leftover administrative files
git worktree prune
```

---

## Section 4: TypeScript Helper — Worktree Review Launcher

```typescript
#!/usr/bin/env ts-node
// scripts/review-pr.ts
// Usage: ts-node scripts/review-pr.ts 456

import { execSync, spawnSync } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';

const prNumber = process.argv[2];
if (!prNumber) {
  console.error('Usage: review-pr.ts <pr-number>');
  process.exit(1);
}

const repoRoot = execSync('git rev-parse --show-toplevel').toString().trim();
const repoName = path.basename(repoRoot);
const parentDir = path.dirname(repoRoot);

// Get the PR branch name via gh CLI
const branchJson = execSync(
  `gh pr view ${prNumber} --json headRefName`
).toString();
const { headRefName } = JSON.parse(branchJson) as { headRefName: string };

const worktreePath = path.join(parentDir, `${repoName}--pr-${prNumber}`);

if (fs.existsSync(worktreePath)) {
  console.log(`Worktree already exists at ${worktreePath}`);
} else {
  console.log(`Fetching origin and creating worktree at ${worktreePath}...`);
  execSync('git fetch origin', { stdio: 'inherit' });
  execSync(
    `git worktree add "${worktreePath}" origin/${headRefName}`,
    { stdio: 'inherit' }
  );
}

// Install deps
const hasPackageJson = fs.existsSync(path.join(worktreePath, 'package.json'));
if (hasPackageJson) {
  console.log('Installing dependencies...');
  spawnSync('npm', ['ci'], { cwd: worktreePath, stdio: 'inherit' });
}

console.log(`\nWorktree ready: ${worktreePath}`);
console.log(`Branch: ${headRefName}`);
console.log(`\nTo clean up: git worktree remove "${worktreePath}"`);
```

---

## Anti-patterns

- Do not place the worktree **inside** the repository directory — Git will confuse it with untracked files. Always use a sibling directory (`../`) or a completely separate path.
- Do not run `npm install` (instead of `npm ci`) in a worktree if you share `node_modules` via symlink — the installs will conflict.
- Do not forget to remove the worktree after merging. Stale worktrees accumulate and confuse `git worktree list`.
- Do not use `git checkout` in the PR worktree to switch to your main branch — each worktree locks its branch; Git will refuse to check out a branch already checked out elsewhere.

## Gotchas

- **Shared `.git` object store**: both worktrees share the same object database. A `git gc` in one affects the other. This is a feature (no duplication) but be aware.
- **Submodules**: submodules are not automatically initialised in the new worktree. Run `git submodule update --init --recursive` inside it.
- **IDE project files**: some IDEs (IntelliJ, Xcode) store absolute paths in project files; opening a worktree as a new project may require re-indexing.
- **Environment variables**: if your `.env` file is gitignored and project-specific, copy or symlink it into the worktree manually.
- **Branch lock**: if the PR branch is already checked out in another worktree (e.g., CI), `git worktree add` will fail. Use `git worktree add -b local-review-456 ../myrepo--pr-456 origin/feature/teammate-widget` to create a local tracking branch.

## Verification

```bash
# Confirm two worktrees exist and point to different branches
git worktree list --porcelain
# worktree /path/to/project
# HEAD <commit-sha>...
# branch refs/heads/feature/auth-refactor
#
# worktree /path/to/project
# HEAD <commit-sha>...
# branch refs/heads/feature/teammate-widget

# Confirm each worktree has no cross-contamination
pushd ../myrepo--pr-456 && git status && popd

# Confirm removal is clean
git worktree remove ../myrepo--pr-456 && git worktree list
```

## Related

- `documentation/docs/policies/worktree/git-worktree-stash-vs-worktree-comparison.md`
- `documentation/docs/policies/worktree/git-worktree-release-branch-hotfix-parallel.md`
- `documentation/docs/policies/worktree/git-worktree-ci-parallel-test-suites.md`

## Sources

- https://git-scm.com/docs/git-worktree
- https://git-scm.com/book/en/v2/Git-Tools-Advanced-Merging
- https://cli.github.com/manual/gh_pr_review
