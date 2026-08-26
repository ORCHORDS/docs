# Git Worktree: Maintaining Release Branches and Cherry-Picking Hotfixes

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your team ships from a `release/2.x` branch while `main` advances rapidly. A critical bug is fixed on `main` and must be backported without switching away from active development work. Running two worktrees — one for `main`, one for `release/2.x` — lets you cherry-pick commits, run tests in both trees simultaneously, then tag and push the release, all without a single `git checkout`.

## Context

- Semantic-versioned release train (e.g., `release/2.4`, `release/3.0`)
- Git 2.15+
- Node.js monorepo or Go service; bash shell
- CI: GitHub Actions with matrix builds

---

## Section 1: Setting Up the Release Worktree

```bash
# From your main working tree (checked out on main)
git fetch origin

# Check out the release branch into a sibling directory
git worktree add ../myrepo--release-2.4 origin/release/2.4

# Verify
git worktree list
# /path/to/project                  c1d2e3f [main]
# /path/to/project    a0b1c2d [release/2.4]

# Install deps in the release worktree (independent node_modules)
pushd ../myrepo--release-2.4
npm ci
popd
```

---

## Section 2: Cherry-Picking a Hotfix from Main into the Release Worktree

```bash
# Find the commit SHA of the hotfix on main
git log --oneline main | head -20
# c1d2e3f fix(auth): prevent token replay on concurrent requests  <-- this one
# b0a9d8c feat(api): add pagination to /users endpoint
# ...

HOTFIX_SHA="c1d2e3f"

# Cherry-pick into the release branch worktree
pushd ../myrepo--release-2.4

git cherry-pick "$HOTFIX_SHA"
# If conflicts arise:
# git cherry-pick --continue   (after resolving)
# git cherry-pick --abort      (to bail out)

# Verify the commit landed
git log --oneline -3
# c1d2e3f fix(auth): prevent token replay on concurrent requests
# a0b1c2d chore(release): bump 2.4.1
# 9f8e7d6 feat(widget): add dark mode toggle

popd

# Run tests in BOTH worktrees simultaneously (background jobs)
(
  cd /path/to/project && npm test 2>&1 | sed 's/^/[main] /'
) &
MAIN_PID=$!

(
  cd /path/to/project && npm test 2>&1 | sed 's/^/[release] /'
) &
RELEASE_PID=$!

wait $MAIN_PID && echo "main: PASS" || echo "main: FAIL"
wait $RELEASE_PID && echo "release: PASS" || echo "release: FAIL"
```

---

## Section 3: Tagging and Pushing the Release

```bash
pushd ../myrepo--release-2.4

# Bump version (example for Node.js)
npm version patch --no-git-tag-version
# Outputs: v2.4.1

# Update changelog manually or via script
NEW_VERSION=$(node -p "require('./package.json').version")
echo "## $NEW_VERSION — $(date +%Y-%m-%d)" | cat - CHANGELOG.md > /tmp/cl && mv /tmp/cl CHANGELOG.md

# Commit the version bump
git add package.json package-lock.json CHANGELOG.md
git commit -m "chore(release): bump ${NEW_VERSION}"

# Create an annotated tag
git tag -a "v${NEW_VERSION}" -m "Release ${NEW_VERSION}: cherry-picked auth hotfix"

# Push branch and tag
git push origin release/2.4
git push origin "v${NEW_VERSION}"

popd

# Trigger GitHub release from the tag (optional)
gh release create "v${NEW_VERSION}" \
  --title "v${NEW_VERSION}" \
  --notes "Hotfix: prevent token replay on concurrent requests (backport from main)" \
  --target release/2.4
```

---

## Section 4: TypeScript Release Script

```typescript
#!/usr/bin/env ts-node
// scripts/release-hotfix.ts
// Usage: ts-node scripts/release-hotfix.ts <hotfix-sha> <release-branch>
// Example: ts-node scripts/release-hotfix.ts c1d2e3f release/2.4

import { execSync } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';

const [hotfixSha, releaseBranch] = process.argv.slice(2);
if (!hotfixSha || !releaseBranch) {
  console.error('Usage: release-hotfix.ts <hotfix-sha> <release-branch>');
  process.exit(1);
}

const repoRoot = execSync('git rev-parse --show-toplevel').toString().trim();
const repoName = path.basename(repoRoot);
const parentDir = path.dirname(repoRoot);
const slug = releaseBranch.replace(/\//g, '-');
const worktreePath = path.join(parentDir, `${repoName}--${slug}`);

const run = (cmd: string, cwd = repoRoot) => {
  console.log(`$ ${cmd}`);
  return execSync(cmd, { cwd, stdio: 'inherit' });
};

// 1. Ensure worktree exists
if (!fs.existsSync(worktreePath)) {
  run(`git fetch origin`);
  run(`git worktree add "${worktreePath}" origin/${releaseBranch}`);
}

// 2. Install deps
if (fs.existsSync(path.join(worktreePath, 'package.json'))) {
  run('npm ci', worktreePath);
}

// 3. Cherry-pick
run(`git cherry-pick ${hotfixSha}`, worktreePath);

// 4. Run tests
run('npm test', worktreePath);

// 5. Bump version
const pkgPath = path.join(worktreePath, 'package.json');
const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
const [major, minor, patch] = pkg.version.split('.').map(Number);
pkg.version = `${major}.${minor}.${patch + 1}`;
fs.writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + '\n');

run(`git add package.json`, worktreePath);
run(`git commit -m "chore(release): bump ${pkg.version}"`, worktreePath);
run(`git tag -a "v${pkg.version}" -m "Hotfix release ${pkg.version}"`, worktreePath);
run(`git push origin ${releaseBranch}`, worktreePath);
run(`git push origin v${pkg.version}`, worktreePath);

console.log(`\nReleased v${pkg.version} on ${releaseBranch}`);
```

---

## Anti-patterns

- Do not cherry-pick directly on `main` into the release branch without a worktree — you risk accidentally committing release-only changes onto `main`.
- Do not create the release worktree inside the repo directory (e.g., `./releases/2.4`) — Git tracks it as untracked content and `.gitignore` entries become messy.
- Do not share `node_modules` between worktrees via symlinks when the release branch has different dependency versions than `main`.
- Do not tag before tests pass in the release worktree — the tag is almost impossible to cleanly retract from remotes once pushed.

## Gotchas

- **Cherry-pick conflicts**: if the hotfix commit has context that doesn't exist in the release branch (because it depends on other `main` commits), cherry-pick will conflict. Resolve carefully; use `git diff HEAD origin/release/2.4` to understand the delta.
- **Annotated vs lightweight tags**: prefer annotated tags (`-a`) for releases — they carry a tagger, date, and message, and are returned by `git describe`.
- **npm version and git tag**: `npm version patch` by default creates a git tag. Use `--no-git-tag-version` to prevent it from tagging so you can create the annotated tag yourself.
- **Worktree branch lock**: once the release branch is checked out in a worktree, you cannot check it out in your main tree. CI pipelines that do `git checkout release/2.4` will fail if the worktree is still registered.

## Verification

```bash
# Confirm cherry-pick is in release branch log
git log origin/release/2.4 --oneline | grep "$HOTFIX_SHA"

# Confirm tag exists and points to the right commit
git show v2.4.1 --stat

# Confirm worktree is removed after release
git worktree remove ../myrepo--release-2.4
git worktree list
```

## Related

- `documentation/docs/policies/worktree/git-worktree-code-review-parallel-checkout.md`
- `documentation/docs/policies/worktree/git-worktree-ci-parallel-test-suites.md`
- `documentation/docs/policies/worktree/git-worktree-prune-cleanup-automation.md`

## Sources

- https://git-scm.com/docs/git-worktree
- https://git-scm.com/docs/git-cherry-pick
- https://docs.npmjs.com/cli/commands/npm-version
- https://cli.github.com/manual/gh_release_create
