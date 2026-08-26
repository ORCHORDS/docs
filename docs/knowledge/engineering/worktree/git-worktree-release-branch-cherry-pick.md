# Git Worktree — Release Branch Cherry-Pick Workflow

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You are actively developing on `main` but need to simultaneously maintain a `release/v2` branch for a production hotfix. Switching branches halts your in-progress work and risks merge pollution. You need a clean, parallel workspace for the release branch.

---

## Context

Release branches live alongside `main` but accept only curated commits — typically cherry-picks of targeted bugfixes rather than full merges. Using `git worktree` you can keep the `release/v2` branch checked out in `../release-v2` permanently during the release window. Hotfixes committed on `main` can be cherry-picked into the release worktree without ever interrupting main development. When the release is ready, you tag and push from the release worktree, then remove it. This workflow is especially clean for Cloudflare Workers projects where `wrangler deploy` is environment-specific and you may need to deploy from the release branch to a staging environment independently.

---

## Section 1 — Setup the Release Worktree

```bash
# Create (or track) the release branch and add a worktree for it
git fetch origin
git worktree add ../release-v2 release/v2

# If release/v2 does not exist yet, create it from a stable tag or commit
git worktree add -b release/v2 ../release-v2 v2.0.0

# Confirm state
git worktree list
# /path/to/project     abc1234 [main]
# /path/to/project  tag2345 [release/v2]

# Install dependencies in the release worktree
cd ../release-v2 && npm ci
```

---

## Section 2 — Cherry-Picking Hotfixes from main

```bash
# On main — commit a hotfix
cd /path/to/project
git add src/auth/token.ts
git commit -m "fix(auth): handle expired token edge case (refs #418)"

# Capture the commit SHA
HOTFIX_SHA=$(git rev-parse HEAD)
echo "Hotfix SHA: $HOTFIX_SHA"

# Switch to the release worktree and cherry-pick
cd ../release-v2
git cherry-pick "$HOTFIX_SHA"

# Resolve any conflicts if they arise
# git cherry-pick --continue  (after resolving)

# Cherry-pick a range of commits if needed
git cherry-pick abc1234^..def5678

# Push the cherry-picked commit to the release branch
git push origin release/v2
```

```typescript
// src/auth/token.ts — the hotfixed file (shared context)
export function validateToken(token: string, env: Env): boolean {
  if (!token || token.trim() === '') return false;
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    // Fix: check exp field exists before comparing
    if (payload.exp !== undefined && payload.exp < Date.now() / 1000) {
      return false;
    }
    return true;
  } catch {
    return false;
  }
}

interface Env {
  JWT_SECRET: string;
}
```

---

## Section 3 — Tagging and Deploying from the Release Worktree

```bash
# Tag the release from within the release worktree
cd ../release-v2
git tag -a v2.0.1 -m "Release v2.0.1 — hotfix expired token"
git push origin v2.0.1
git push origin release/v2

# Deploy the release branch to production via wrangler
npx wrangler deploy --env production

# Verify the deployed version
npx wrangler deployments list

# Keep main in sync — merge release back to catch the cherry-pick
cd /path/to/project
git fetch origin
git merge origin/release/v2 --no-ff -m "chore: sync release/v2 hotfixes back to main"
git push origin main

# Remove the release worktree when the release window closes
git worktree remove ../release-v2
git worktree prune
```

---

## Anti-patterns

- **Merging main into release/v2 instead of cherry-picking** — This drags in unvetted in-progress commits. Always cherry-pick specific SHAs to keep the release branch clean.
- **Tagging from the main worktree on the wrong branch** — If `HEAD` in the main worktree is on `main`, `git tag` will tag the wrong commit. Always cd into the release worktree before tagging.
- **Skipping `npm ci` in the release worktree** — The release branch may have a different `package-lock.json` than `main`. Always run `npm ci` (not `npm install`) to ensure a reproducible install.
- **Deleting the release worktree before pushing the tag** — Remove the worktree only after `git push origin v2.0.1` has succeeded and been verified.

---

## Gotchas

- Cherry-pick SHA references must be copied exactly — short SHAs can be ambiguous in repos with many commits.
- `wrangler deploy` reads `wrangler.toml` from the current directory, which inside the release worktree points to the release branch config. Double-check environment bindings before deploying.
- If `release/v2` was created from a tag rather than a branch tip, `git push origin release/v2` requires the upstream to be set: `git push --set-upstream origin release/v2`.
- Tags created in a worktree are visible repo-wide immediately — avoid duplicate tag names by checking `git tag -l` first.
- `git cherry-pick` with `--no-commit` lets you inspect changes before committing — useful when the hotfix requires adaptation for the release branch.

---

## Verification

```bash
# Confirm the tag exists and points to the right commit
git show v2.0.1 --stat

# Confirm the release branch has the cherry-picked fix
cd ../release-v2
git log --oneline -5

# Confirm the production deployment is live
curl https://my-worker.example.com/health

# Confirm the release worktree is gone
git worktree list
```

---

## Related

- `git-worktree-parallel-feature-development.md`
- `git-submodule-shared-workers-library.md`

---

## Sources

- Git Cherry-Pick Documentation — https://git-scm.com/docs/git-cherry-pick
- Wrangler Deploy Reference — https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- Semantic Versioning — https://semver.org
