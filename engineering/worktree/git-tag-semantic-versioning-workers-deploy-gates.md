# Git Tags as Semantic Versioning Deploy Gates for Cloudflare Workers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Deployments to Cloudflare Workers production are triggered manually or by every merge to `main`, causing accidental releases and no clear audit trail of what version is live. The team needs immutable, human-readable deploy gates so that only a deliberate version tag can trigger a production deploy.

## Context

Cloudflare Workers has no native concept of a release artefact — `wrangler deploy` pushes whatever source is present. Introducing semver git tags as the single source of truth for production readiness closes this gap: a tag like `workers-api@2.4.1` gates the GitHub Actions workflow, doubles as the `version` field in the uploaded Worker metadata, and appears in Cloudflare's dashboard for instant rollback identification. This pattern integrates cleanly with `release-please` or manual tagging in a trunk-based development flow.

## Tagging Strategy for Workers Environments

Use scoped tags to distinguish workers in a monorepo. Adopt the pattern `<worker-name>@<semver>`:

```bash
# Tag a specific worker for release
git tag workers-api@2.4.1 -m "chore(workers-api): release 2.4.1"
git tag workers-auth@1.1.0 -m "chore(workers-auth): release 1.1.0"

# Push tags explicitly — they are not pushed by default
git push origin workers-api@2.4.1
git push origin workers-auth@1.1.0

# List all tags for a worker in version order
git tag --list 'workers-api@*' --sort=version:refname

# Show what commit a tag points to
git rev-list -n 1 workers-api@2.4.1
```

Enforce the naming pattern with a `prepare-commit-msg` hook that rejects malformed tag names:

```bash
#!/usr/bin/env bash
# .git/hooks/pre-push
while IFS=' ' read -r local_ref local_sha remote_ref remote_sha; do
  if [[ "$local_ref" == refs/tags/* ]]; then
    tag_name="${local_ref#refs/tags/}"
    if ! [[ "$tag_name" =~ ^[a-z0-9-]+@[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      echo "ERROR: Tag '$tag_name' must match <worker-name>@<semver>"
      exit 1
    fi
  fi
done
```

## GitHub Actions Deploy Gate on Tag Push

Trigger the production deploy workflow only on matching tag pushes, never on branch pushes:

```yaml
# .github/workflows/deploy-workers-production.yml
name: Deploy Workers (Production)

on:
  push:
    tags:
      - 'workers-*@[0-9]+.[0-9]+.[0-9]+'

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.ref }}

      - name: Parse worker name and version from tag
        id: tag
        run: |
          TAG="${GITHUB_REF_NAME}"
          WORKER="${TAG%@*}"
          VERSION="${TAG#*@}"
          echo "worker=$WORKER" >> "$GITHUB_OUTPUT"
          echo "version=$VERSION" >> "$GITHUB_OUTPUT"

      - name: Install pnpm and dependencies
        uses: pnpm/action-setup@v4
        with:
          version: 9

      - run: pnpm install --frozen-lockfile

      - name: Deploy ${{ steps.tag.outputs.worker }} v${{ steps.tag.outputs.version }}
        working-directory: workers/${{ steps.tag.outputs.worker }}
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          WORKER_VERSION: ${{ steps.tag.outputs.version }}
        run: |
          pnpm wrangler deploy \
            --name "${{ steps.tag.outputs.worker }}" \
            --var VERSION:"$WORKER_VERSION"
```

## Validating Semver Tags Before Deployment

Add a pre-deploy validation step that checks the tag points to a commit on `main` and that the version in `package.json` matches the tag:

```typescript
// scripts/validate-deploy-tag.ts
import { execSync } from "node:child_process";

const tag = process.env.GITHUB_REF_NAME!;
const [workerName, semver] = tag.split("@");

// 1. Confirm the tagged commit is reachable from main
const taggedSha = execSync(`git rev-list -n 1 ${tag}`).toString().trim();
const mainSha = execSync("git rev-parse origin/main").toString().trim();
const mergeBase = execSync(
  `git merge-base ${taggedSha} ${mainSha}`
).toString().trim();

if (mergeBase !== taggedSha) {
  console.error(`Tag ${tag} does not point to a commit on main`);
  process.exit(1);
}

// 2. Confirm package.json version matches the semver in the tag
const pkg = JSON.parse(
  execSync(`cat workers/${workerName}/package.json`).toString()
);
if (pkg.version !== semver) {
  console.error(
    `Tag semver ${semver} does not match package.json version ${pkg.version}`
  );
  process.exit(1);
}

console.log(`✓ Tag ${tag} validated — deploying ${workerName}@${semver}`);
```

```yaml
# In the deploy workflow, add before the wrangler step:
- name: Validate deploy tag
  run: npx tsx scripts/validate-deploy-tag.ts
  env:
    GITHUB_REF_NAME: ${{ github.ref_name }}
```

## Anti-patterns

- Using branch pushes (`on: push: branches: [main]`) for production deploys — every merge triggers a deploy with no explicit version signal.
- Creating tags locally but forgetting `git push --tags` — the tag exists only on the developer's machine and CI never fires.
- Using lightweight tags (no `-m` message) for production releases — annotated tags carry tagger identity and timestamp, which appear in `git log --tags` and are essential for audit trails.
- Naming tags with only a semver (e.g. `v2.4.1`) in a monorepo — it is ambiguous which worker the version refers to.

## Gotchas

- GitHub Actions `github.ref_name` on a tag event contains the full tag name (e.g. `workers-api@2.4.1`), not just the semver portion — always parse it explicitly.
- Deleting and recreating a tag to fix a mistake causes CI to re-fire the deploy workflow; use `git tag -d` locally plus `git push origin :refs/tags/<tag>` then recreate — and add a Slack alert so the team is aware.
- `wrangler deploy` does not natively accept a `--version` flag; pass version metadata through `--var` or via a `[vars]` override in `wrangler.toml` populated at CI time.

## Verification

```bash
# List all production tags sorted by version for a given worker
git tag --list 'workers-api@*' --sort=-version:refname | head -5

# Confirm the latest tag's commit is on main
git log --oneline main | grep "$(git rev-list -n 1 workers-api@2.4.1)"

# Check the annotated tag metadata
git show workers-api@2.4.1 --no-patch

# Verify the Cloudflare dashboard shows the correct version
wrangler deployments list --name workers-api
```

## Related

- `worktree/semantic-versioning-2026.md`
- `worktree/github-actions-wrangler-deploy-pipeline.md`
- `worktree/release-please-automated-releases.md`
- `worktree/wrangler-environments-staging-production.md`

## Sources

- https://git-scm.com/book/en/v2/Git-Basics-Tagging
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#push
