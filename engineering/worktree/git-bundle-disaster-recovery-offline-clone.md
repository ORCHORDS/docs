# Git Bundle Files: Disaster Recovery and Offline Repository Distribution

- Date: 2026-08-22
- Author: example.com
- Status: production

## Self-Contained Repository Snapshots for When the Remote Is Unavailable

A git bundle is a single file that contains a complete or partial git repository — pack data plus ref advertisements — in a format that git treats identically to a remote. You can clone from it, fetch from it, and inspect it without any network connection or running git daemon. The bundle is portable: copy it to a USB drive, upload it to object storage, email it, or check it into an archive system.

The disaster recovery angle is straightforward: if GitHub, GitLab, or your self-hosted Gitea instance becomes unavailable, any team member with the latest bundle can reconstruct the full repository in seconds. The offline distribution angle matters for air-gapped environments, developer onboarding on slow connections, and Cloudflare Workers deploy pipelines that need the full object store without waiting for a fresh clone.

Bundles also support incremental updates via prerequisite commits: a bundle can declare "I contain everything reachable from HEAD that is not already reachable from commit `abc1234`." A team receiving the bundle can fetch from it directly into an existing clone, downloading only the delta.

## Context

Stack: Cloudflare Workers monorepo, GitHub Actions for bundle generation, Cloudflare R2 for bundle storage (accessed via the Workers runtime or `wrangler r2`). Bundles are generated nightly and on every release tag.

## Creating Bundle Files

```bash
# Full bundle: everything reachable from all refs
git bundle create full-repo.bundle --all

# Single-branch bundle
git bundle create main-branch.bundle main

# Incremental bundle: commits reachable from HEAD not in a previous bundle
# The prerequisite commit is the last commit covered by the previous bundle.
PREV_TIP=$(git rev-parse HEAD~500)
git bundle create incremental.bundle \
  --not "$PREV_TIP" \
  HEAD

# Bundle with tags included
git bundle create release-v3.bundle \
  --tags \
  main \
  "refs/tags/v3.*"

# Verify a bundle before distributing it
git bundle verify full-repo.bundle

# List the refs a bundle advertises
git bundle list-heads full-repo.bundle
```

## Cloning and Fetching from a Bundle

```bash
# Clone from a bundle (creates a new local repository)
git clone full-repo.bundle local-repo
cd local-repo
git remote set-url origin git@github.com:example-org/example-repo.git

# Fetch from an incremental bundle into an existing clone
# Git fetches only the objects the bundle contains that the local repo lacks.
git fetch incremental.bundle HEAD:refs/remotes/bundle/main

# Fetch all heads a bundle advertises
git fetch full-repo.bundle '*:refs/remotes/bundle/*'

# Verify the bundle satisfies all prerequisites before fetching
git bundle verify incremental.bundle
```

## Storing Bundles in Cloudflare R2

Bundles are ideal R2 objects: they are immutable once created, large (100 MB – 2 GB range), and accessed infrequently. R2's zero-egress pricing makes them cost-effective for internal distribution.

```bash
# Upload a bundle using wrangler r2
wrangler r2 object put \
  git-bundles/monorepo/full-$(date +%Y%m%d).bundle \
  --file=full-repo.bundle \
  --bucket=orchords-git-bundles \
  --content-type=application/octet-stream

# List available bundles
wrangler r2 object list git-bundles/monorepo/ \
  --bucket=orchords-git-bundles

# Download the latest full bundle
wrangler r2 object get \
  git-bundles/monorepo/full-$(date +%Y%m%d).bundle \
  --file=recovered.bundle \
  --bucket=orchords-git-bundles
```

The following Cloudflare Worker serves bundle files from R2 with a signed URL pattern for authenticated download:

```typescript
// workers/bundle-server/src/index.ts
import { Env } from "./types";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Only allow authenticated requests
    const authHeader = request.headers.get("Authorization");
    if (authHeader !== `Bearer ${env.BUNDLE_API_TOKEN}`) {
      return new Response("Unauthorized", { status: 401 });
    }

    // Route: GET /bundles/latest or GET /bundles/:date
    const match = url.pathname.match(/^\/bundles\/([^/]+)$/);
    if (!match || request.method !== "GET") {
      return new Response("Not found", { status: 404 });
    }

    const dateKey = match[1] === "latest"
      ? new Date().toISOString().slice(0, 10).replace(/-/g, "")
      : match[1];

    const objectKey = `git-bundles/monorepo/full-${dateKey}.bundle`;
    const object = await env.GIT_BUNDLES.get(objectKey);

    if (!object) {
      return new Response(`Bundle not found for date ${dateKey}`, { status: 404 });
    }

    return new Response(object.body, {
      headers: {
        "Content-Type": "application/octet-stream",
        "Content-Disposition": `attachment; filename="monorepo-${dateKey}.bundle"`,
        "Cache-Control": "private, max-age=86400",
      },
    });
  },
};
```

```typescript
// workers/bundle-server/src/types.ts
export interface Env {
  GIT_BUNDLES: R2Bucket;
  BUNDLE_API_TOKEN: string;
}
```

## Automated Bundle Generation in GitHub Actions

```yaml
# .github/workflows/nightly-bundle.yml
name: Nightly Git Bundle

on:
  schedule:
    - cron: "0 1 * * *"  # 01:00 UTC daily
  push:
    tags:
      - "v*"
  workflow_dispatch:

jobs:
  bundle:
    runs-on: ubuntu-latest
    timeout-minutes: 20

    steps:
      - name: Full clone
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
          fetch-tags: true

      - name: Create full bundle
        run: |
          DATE=$(date +%Y%m%d)
          git bundle create "monorepo-full-${DATE}.bundle" --all
          git bundle verify "monorepo-full-${DATE}.bundle"
          echo "BUNDLE_FILE=monorepo-full-${DATE}.bundle" >> "$GITHUB_ENV"
          echo "BUNDLE_DATE=${DATE}" >> "$GITHUB_ENV"

      - name: Upload bundle to R2
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          npx wrangler r2 object put \
            "git-bundles/monorepo/full-${BUNDLE_DATE}.bundle" \
            --file="${BUNDLE_FILE}" \
            --bucket=orchords-git-bundles \
            --content-type=application/octet-stream

      - name: Create incremental bundle (for tag pushes)
        if: startsWith(github.ref, 'refs/tags/')
        run: |
          TAG="${{ github.ref_name }}"
          PREV_TAG=$(git describe --tags --abbrev=0 "${TAG}^" 2>/dev/null || true)
          if [[ -n "$PREV_TAG" ]]; then
            git bundle create "monorepo-since-${PREV_TAG}.bundle" \
              "${PREV_TAG}..${TAG}" \
              "refs/tags/${TAG}"
            git bundle verify "monorepo-since-${PREV_TAG}.bundle"
            npx wrangler r2 object put \
              "git-bundles/monorepo/incremental-${PREV_TAG}-to-${TAG}.bundle" \
              --file="monorepo-since-${PREV_TAG}.bundle" \
              --bucket=orchords-git-bundles \
              --content-type=application/octet-stream
          fi
```

## Disaster Recovery Runbook

```bash
# Step 1: Download the most recent bundle
curl -H "Authorization: Bearer $BUNDLE_TOKEN" \
  "https://bundles.example.com/bundles/latest" \
  -o recovered.bundle

# Step 2: Verify integrity
git bundle verify recovered.bundle

# Step 3: Clone from the bundle
git clone recovered.bundle orchords-monorepo
cd orchords-monorepo

# Step 4: Re-point remote to the real origin once available
git remote set-url origin git@github.com:example-org/example-repo.git

# Step 5: Fetch any commits that landed after the bundle was created
git fetch origin --all --tags

# Step 6: Verify you are current
git log --oneline origin/main..HEAD  # should be empty
```

## Anti-patterns

- Storing bundles only locally: the bundle's value is having an off-site copy; always upload immediately after creation
- Creating incremental bundles without verifying prerequisite commits exist in the target: `git bundle verify` will fail on the recipient's machine if their clone does not contain the prerequisite
- Sharing bundles containing secrets in `.env` or config files checked in to git: bundle contents are the full git history; scrub secrets before bundling
- Using bundles as a substitute for proper backup (snapshots + replication): bundles cover object data but not GitHub issue/PR metadata, wikis, or Actions secrets
- Omitting `--tags` from the bundle command: tag objects are not included by default; releases become unresolvable from the bundle

## Gotchas

- A bundle created with `--all` includes stash refs (`refs/stash`) if any exist; recipients may be confused by unexpected stash entries after cloning
- The bundle format uses pack format v2; Git 1.x clients may not support large bundles (> 4 GB packs); use Git 2.29+ on both sides
- `git clone <bundle>` sets `origin` to the bundle file path, not the original remote; always `git remote set-url origin` after recovery
- Incremental bundles become unverifiable if the prerequisite commit is later garbage-collected from the recipient's repo (e.g., after a `git gc --prune=all`)
- R2 does not enforce MIME types at download time; always name the file `.bundle` so git recognises it without the `-o` flag alternative

## Verification

```bash
# Verify bundle integrity and list advertised refs
git bundle verify monorepo-full-$(date +%Y%m%d).bundle
git bundle list-heads monorepo-full-$(date +%Y%m%d).bundle

# Confirm clone from bundle is complete
git clone monorepo-full-$(date +%Y%m%d).bundle /tmp/verify-clone
cd /tmp/verify-clone
git log --oneline -5
git tag | tail -5
git fsck --full
```

## Related

- [git-maintenance-scheduled-background-pack-optimization.md](git-maintenance-scheduled-background-pack-optimization.md)
- [git-lfs-2026.md](git-lfs-2026.md)
- [ci-cd-pipeline-2026.md](ci-cd-pipeline-2026.md)
- [release-please-semantic-release.md](release-please-semantic-release.md)
- [hotfix-process.md](hotfix-process.md)

## Sources

- https://git-scm.com/docs/git-bundle
- https://developers.cloudflare.com/r2/
- https://developers.cloudflare.com/workers/wrangler/commands/#r2-object
- Pro Git Book, Chapter 7.12 — Bundling
