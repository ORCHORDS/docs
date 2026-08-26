# Release Branch Strategy for Production Cloudflare Workers Deployments

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your Workers team ships from `main` continuously, but you need the ability to freeze a release candidate, apply targeted hotfixes without pulling in unrelated in-progress work from `main`, and maintain a clear audit trail of what is running in production at any point in time. You also need automated deployment triggered by a git tag rather than a branch push, so production deploys are always traceable to an immutable artifact.

## Context

Release branches coexist with trunk-based development: `main` flows continuously, but when a release is cut a branch (`release/v1.4`) is forked from `main` at the release SHA. Only cherry-picked hotfixes land on release branches — no feature work. The branch is tagged (`v1.4.0`, `v1.4.1`) and each tag triggers a production deploy. Release branches are closed (not deleted, just frozen) after the next major release ships.

For Cloudflare Workers this maps naturally:
- `main` → continuous deploy to `staging` Worker environment
- `release/vX.Y` → deploy to `production` environment, triggered by tag
- `wrangler.toml` environments separate staging and production bindings

## Solution

### 1. wrangler.toml environment configuration

```toml
# wrangler.toml
name = "api-gateway"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[env.staging]
name = "api-gateway-staging"
vars = { ENVIRONMENT = "staging", LOG_LEVEL = "debug" }
kv_namespaces = [
  { binding = "CACHE", id = "<staging-kv-id>" }
]

[env.production]
name = "api-gateway"
vars = { ENVIRONMENT = "production", LOG_LEVEL = "warn" }
kv_namespaces = [
  { binding = "CACHE", id = "<production-kv-id>" }
]
routes = [
  { pattern = "api.example.com/*", zone_name = "example.com" }
]
```

### 2. Release branch creation script

```bash
#!/bin/bash
# scripts/cut-release.sh
# Usage: ./scripts/cut-release.sh 1.4.0

set -euo pipefail

VERSION="${1:?Usage: $0 <version> (e.g. 1.4.0)}"
MAJOR_MINOR=$(echo "$VERSION" | cut -d. -f1-2)
BRANCH="release/v${MAJOR_MINOR}"
TAG="v${VERSION}"

echo "Cutting release $TAG from main..."

# Ensure we are on main and up to date
git checkout main
git pull origin main

# Create release branch
git checkout -b "$BRANCH"

# Bump version in package.json
npm version "$VERSION" --no-git-tag-version
git add package.json package-lock.json
git commit -m "chore(release): bump version to $VERSION"

# Tag the release
git tag -a "$TAG" -m "Release $TAG"

# Push branch and tag
git push origin "$BRANCH"
git push origin "$TAG"

echo "Release branch '$BRANCH' and tag '$TAG' pushed."
echo "CI will deploy $TAG to production automatically."
```

### 3. Version bump helper (TypeScript)

```typescript
// scripts/prepare-release.ts
import { execSync } from 'child_process';
import { readFileSync, writeFileSync } from 'fs';

interface PackageJson {
  version: string;

}

function bumpVersion(current: string, type: 'major' | 'minor' | 'patch'): string {
  const [major, minor, patch] = current.split('.').map(Number);
  switch (type) {
    case 'major': return `${major + 1}.0.0`;
    case 'minor': return `${major}.${minor + 1}.0`;
    case 'patch': return `${major}.${minor}.${patch + 1}`;
  }
}

const bumpType = (process.argv[2] ?? 'patch') as 'major' | 'minor' | 'patch';
const pkgPath = 'package.json';
const pkg: PackageJson = JSON.parse(readFileSync(pkgPath, 'utf-8'));
const newVersion = bumpVersion(pkg.version, bumpType);

pkg.version = newVersion;
writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + '\n');

console.log(`Bumped ${pkg.version} → ${newVersion}`);
```

### 4. Tag-triggered production deploy (GitHub Actions)

```yaml
# .github/workflows/deploy-production.yml
name: Deploy to Production

on:
  push:
    tags:
      - 'v[0-9]+.[0-9]+.[0-9]+'

jobs:
  validate-tag:
    runs-on: ubuntu-latest
    outputs:
      version: ${{ steps.parse.outputs.version }}
    steps:
      - name: Parse version from tag
        id: parse
        run: |
          TAG="${GITHUB_REF#refs/tags/}"
          echo "version=${TAG#v}" >> $GITHUB_OUTPUT
          echo "Deploying tag: $TAG"

  deploy:
    needs: validate-tag
    runs-on: ubuntu-latest
    environment: production   # requires manual approval if configured
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.ref }}  # checkout the exact tag commit

      - uses: actions/setup-node@v4
        with: { node-version: '22', cache: 'npm' }

      - run: npm ci

      - name: Run tests against release commit
        run: npx vitest run

      - name: Deploy to production
        run: npx wrangler deploy --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN_PRODUCTION }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ github.ref_name }}
          name: Release ${{ needs.validate-tag.outputs.version }}
          generate_release_notes: true
          token: ${{ secrets.GITHUB_TOKEN }}
```

### 5. Hotfix cherry-pick workflow

```bash
#!/bin/bash
# scripts/hotfix.sh
# Usage: ./scripts/hotfix.sh release/v1.4 abc1234 1.4.1

set -euo pipefail

RELEASE_BRANCH="${1:?Arg 1: release branch (e.g. release/v1.4)}"
COMMIT_SHA="${2:?Arg 2: commit SHA to cherry-pick}"
HOTFIX_VERSION="${3:?Arg 3: new patch version (e.g. 1.4.1)}"
TAG="v${HOTFIX_VERSION}"

git checkout "$RELEASE_BRANCH"
git pull origin "$RELEASE_BRANCH"

echo "Cherry-picking $COMMIT_SHA onto $RELEASE_BRANCH..."
git cherry-pick "$COMMIT_SHA"

# Bump to patch version
npm version "$HOTFIX_VERSION" --no-git-tag-version
git add package.json package-lock.json
git commit -m "chore(release): bump version to $HOTFIX_VERSION"

git tag -a "$TAG" -m "Hotfix release $TAG"
git push origin "$RELEASE_BRANCH"
git push origin "$TAG"

echo "Hotfix tag $TAG pushed. Verify the fix was also merged to main:"
echo "  git log main --oneline | grep $COMMIT_SHA"
```

### 6. Release branch protection rules

```bash
# Apply protection to release branches via GitHub CLI
# Run once per release branch, or use a wildcard pattern in GitHub UI

gh api \
  --method PUT \
  "repos/example-org/example-repo/branches/release%2Fv1.4/protection" \
  --field enforce_admins=false \
  --field required_status_checks='{"strict":true,"contexts":["test","typecheck"]}' \
  --field required_pull_request_reviews='{"required_approving_review_count":1}' \
  --field restrictions=null \
  --field allow_force_pushes=false \
  --field allow_deletions=false
```

In GitHub UI: Settings > Branches > Add rule, pattern `release/*`.

### 7. EOL release branch cleanup

```bash
#!/bin/bash
# scripts/cleanup-release-branches.sh
# Deletes release branches more than N minor versions behind current

set -euo pipefail

KEEP_LAST=2   # keep the two most recent minor release lines

RELEASE_BRANCHES=$(git branch -r | grep 'origin/release/v' | sed 's|.*origin/||' | sort -V)
TOTAL=$(echo "$RELEASE_BRANCHES" | wc -l)
TO_DELETE=$((TOTAL - KEEP_LAST))

if [ "$TO_DELETE" -le 0 ]; then
  echo "Nothing to clean up ($TOTAL release branches, keeping $KEEP_LAST)."
  exit 0
fi

echo "$RELEASE_BRANCHES" | head -n "$TO_DELETE" | while read -r BRANCH; do
  echo "Deleting EOL branch: $BRANCH"
  git push origin --delete "$BRANCH"
done
```

## Implementation Details

- Tags are immutable references; a tagged commit represents an exact, reproducible snapshot of the Worker bundle. Always deploy from a tag, never from a branch HEAD in production.
- The `environment: production` key in the GitHub Actions job triggers the GitHub Environments approval gate if configured — a second person must approve before the deploy runs.
- Hotfixes MUST also be merged (or cherry-picked) to `main` within 24 hours. Failure to do this means the fix is lost at the next release, which is usually discovered at the worst possible time.
- `wrangler deploy --env production` reads the `[env.production]` block from `wrangler.toml`, giving production Workers different KV namespace IDs, routes, and variable values from staging.

## Anti-patterns

- **Deploying directly from `main` to production**: any in-progress feature on `main` ships unintentionally; always deploy from a tag.
- **Merging feature work into a release branch**: release branches are for bug fixes only; features wait for the next release cycle.
- **Tagging `main` directly for releases**: tags on `main` don't prevent future commits from preceding the tag in git history, making `git describe` unreliable.
- **Deleting release branches immediately after release**: keep at least two release lines for rollback and forensics.

## Gotchas

- `npm version` modifies `package.json` AND creates a git tag by default; use `--no-git-tag-version` when the script handles tagging separately.
- `git push origin --delete <tag>` deletes a tag from remote; this is destructive and should be protected against in repository settings.
- GitHub's tag protection rules (`Settings > Tags > Protected tags`) can prevent accidental tag deletion or force-push; enable for `v*`.
- If using `generate_release_notes: true` in `softprops/action-gh-release`, the release notes are derived from PR titles merged since the previous tag — make sure PR titles follow conventional commit format.

## Verification

```bash
# List release branches
git branch -r | grep 'release/'

# Confirm tag points to correct commit
git show v1.4.0 --stat | head -5

# Verify production Worker version header
curl -s https://api.example.com/healthz | jq .version

# Check what tag triggered the last deploy
gh run list --workflow deploy-production.yml --limit 5
```

## Related

- `documentation/categories/worktree/workers-trunk-based-development-workflow.md`
- `documentation/categories/worktree/workers-merge-queue-github-actions.md`
- `documentation/categories/worktree/workers-gitops-auto-deploy-main-branch.md`

## Sources

- https://trunkbaseddevelopment.com/branch-for-release/
- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/using-environments-for-deployment
- https://developers.cloudflare.com/workers/wrangler/environments/
