# Creating Release Snapshots for Workers Deployments with git archive

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Your compliance team requires an immutable snapshot of the exact source code deployed to Cloudflare Workers production at each release, stored in object storage independent of the Git host. You also need to produce a reproducible tarball that a new engineer can unpack and build without cloning the repository or running `pnpm install` against a live registry.

## Context

`git archive` creates a tar or zip file from any tree-ish (branch, tag, commit SHA) without checking out files to disk. Unlike `git clone`, it produces no `.git` directory, so the output is safe to store in R2 or S3 as an immutable release artifact. In a Cloudflare Workers monorepo workflow, `git archive` fills the gap between the tag created by Release Please and the actual wrangler deploy: the snapshot proves what was deployed, satisfies SOC 2 artifact retention requirements, and enables offline rebuilds. The archive can be created locally, in CI, or via a Git server's archive endpoint.

## Creating Archives from Tags and Commits

```bash
# Archive the entire monorepo at a semantic version tag
git archive --format=tar.gz \
  --prefix=monorepo-v1.4.2/ \
  v1.4.2 \
  --output=monorepo-v1.4.2.tar.gz

# Archive only a single Worker's package directory from a tag
git archive --format=tar.gz \
  --prefix=api-gateway-v1.4.2/ \
  v1.4.2:packages/api-gateway \
  --output=api-gateway-v1.4.2.tar.gz

# Archive from the exact commit SHA (more tamper-evident than a tag)
DEPLOY_SHA=$(git rev-parse HEAD)
git archive --format=tar.gz \
  --prefix=api-gateway-${DEPLOY_SHA:0:12}/ \
  "$DEPLOY_SHA":packages/api-gateway \
  --output="api-gateway-${DEPLOY_SHA:0:12}.tar.gz"

# Create a zip instead (useful for Windows-based audit tooling)
git archive --format=zip \
  --prefix=monorepo-v1.4.2/ \
  v1.4.2 \
  --output=monorepo-v1.4.2.zip
```

## Storing Snapshots in Cloudflare R2

```bash
# Upload the snapshot to R2 using wrangler r2 object put
wrangler r2 object put \
  release-snapshots/monorepo-v1.4.2.tar.gz \
  --file=monorepo-v1.4.2.tar.gz \
  --bucket=my-release-archive

# Tag the object with deploy metadata (custom headers via --content-type)
# R2 supports custom metadata via the API; use wrangler for simple uploads
wrangler r2 object put \
  release-snapshots/api-gateway-${DEPLOY_SHA:0:12}.tar.gz \
  --file="api-gateway-${DEPLOY_SHA:0:12}.tar.gz" \
  --bucket=my-release-archive

# Verify the upload is retrievable
wrangler r2 object get \
  release-snapshots/monorepo-v1.4.2.tar.gz \
  --bucket=my-release-archive \
  --file=/tmp/verify-snapshot.tar.gz
tar -tzf /tmp/verify-snapshot.tar.gz | head -20
```

## CI Pipeline Integration

```yaml
# .github/workflows/release-snapshot.yml
name: Release Snapshot

on:
  push:
    tags: ['v*.*.*']

jobs:
  snapshot:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # full history so git archive can resolve tags

      - name: Create monorepo snapshot
        run: |
          TAG=${GITHUB_REF_NAME}
          git archive --format=tar.gz \
            --prefix="${TAG}/" \
            "${TAG}" \
            --output="snapshot-${TAG}.tar.gz"
          echo "SNAPSHOT_FILE=snapshot-${TAG}.tar.gz" >> "$GITHUB_ENV"
          echo "SNAPSHOT_SHA=$(sha256sum snapshot-${TAG}.tar.gz | cut -d' ' -f1)" >> "$GITHUB_ENV"

      - name: Upload to R2
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          npx wrangler r2 object put \
            "release-snapshots/${SNAPSHOT_FILE}" \
            --file="${SNAPSHOT_FILE}" \
            --bucket=my-release-archive

      - name: Record snapshot SHA in release notes
        run: |
          gh release edit "${GITHUB_REF_NAME}" \
            --notes-file <(gh release view "${GITHUB_REF_NAME}" --json body -q .body) \
            --notes "$(gh release view "${GITHUB_REF_NAME}" --json body -q .body)

          **Snapshot SHA-256:** \`${SNAPSHOT_SHA}\`"
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## Excluding Files from the Archive

Use `.gitattributes` to mark files that should be excluded from `git archive` output, such as test fixtures, CI configs, or development tooling:

```bash
# .gitattributes entries to exclude from git archive
echo "**/__tests__/ export-ignore" >> .gitattributes
echo ".github/ export-ignore" >> .gitattributes
echo ".husky/ export-ignore" >> .gitattributes
echo "**/*.test.ts export-ignore" >> .gitattributes
echo "vitest.config.ts export-ignore" >> .gitattributes
echo "turbo.json export-ignore" >> .gitattributes

# Commit the .gitattributes changes
git add .gitattributes
git commit -m "chore: configure git archive export-ignore for release snapshots"

# Test what the archive will contain before tagging
git archive --format=tar HEAD | tar -t | grep -v test | head -40
```

## Anti-patterns

- Archiving from a branch name (`main`) rather than a tag or commit SHA—branch names are mutable, so the archive is not reproducible if history is rewritten.
- Using `git clone --depth 1` and zipping the working directory instead of `git archive`—this includes the `.git` directory and any local uncommitted changes, making the snapshot non-deterministic.
- Skipping the `.gitattributes` `export-ignore` setup—archives bloated with test fixtures and CI configs fail compliance reviews that expect production-only source.
- Storing snapshots only in the GitHub Releases asset store—GitHub imposes retention limits and the snapshots become unavailable if the repository is deleted or moved.

## Gotchas

- `git archive` does not recurse into git submodules by default; if your monorepo uses submodules for shared packages, use `git submodule foreach` in combination or switch to pnpm workspaces.
- The `--prefix` trailing slash is required; omitting it causes all files to be extracted without a containing directory, making multi-version archives impossible to unpack side-by-side.
- R2 object keys are case-sensitive; standardize on lowercase tag names (enforced via branch protection rules) to avoid duplicate snapshot keys differing only in case.

## Verification

```bash
# Confirm the archive contains the expected Worker entry points
tar -tzf monorepo-v1.4.2.tar.gz | grep "src/index.ts"

# Reproduce a build from the snapshot without network access
tar -xzf monorepo-v1.4.2.tar.gz
cd monorepo-v1.4.2
# pnpm install from a local registry mirror or cache
pnpm install --prefer-offline
pnpm turbo run build

# Confirm SHA-256 matches the recorded value
sha256sum monorepo-v1.4.2.tar.gz
```

## Related

- `worktree/git-tag-semantic-versioning-workers-deploy-gates.md`
- `worktree/release-please-automated-releases.md`
- `worktree/wrangler-environments-staging-production.md`
- `worktree/workers-kv-r2-d1-storage-selection.md`

## Sources

- https://git-scm.com/docs/git-archive
- https://developers.cloudflare.com/r2/api/s3/api/
- https://developers.cloudflare.com/workers/wrangler/commands/#r2-object
