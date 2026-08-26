# Changesets Versioning and Automated Release Pipeline for Workers Packages

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your Cloudflare Workers monorepo publishes shared TypeScript packages to npm (a shared KV helpers library, a typed D1 query builder, an auth utilities package) and deploys Workers themselves. Version bumps are done manually, changelogs drift out of date, npm publishes happen from developer laptops with no audit trail, and pre-release testing is ad-hoc. You need an automated pipeline that versions packages via pull request, generates structured changelogs, publishes to npm, creates GitHub releases, and handles pre-release beta tags — all driven by changesets.

## Context

Applies when:
- Monorepo with multiple publishable npm packages alongside deployed Workers
- GitHub Actions for CI/CD
- Conventional Commits or manual changeset authoring
- Wrangler used for Worker deployments (separate from npm publish)
- `pnpm` workspaces

Changesets separates the concern of "what changed" (a developer writes a `.changeset/*.md` file describing the change) from "when to release" (the CI pipeline aggregates changesets into version bumps and publishes on merge to `main`).

## Solution

### Initial setup

```bash
pnpm add -Dw @changesets/cli
pnpm exec changeset init
```

This creates `.changeset/config.json` and `.changeset/README.md`.

### `.changeset/config.json`

```json
{
  "$schema": "https://unpkg.com/@changesets/config@3.0.0/schema.json",
  "changelog": "@changesets/changelog-github",
  "commit": false,
  "fixed": [],
  "linked": [["@myorg/kv-helpers", "@myorg/d1-helpers"]],
  "access": "public",
  "baseBranch": "main",
  "updateInternalDependencies": "patch",
  "ignore": []
}
```

The `linked` array ensures `@myorg/kv-helpers` and `@myorg/d1-helpers` are always released together with the same version number — useful for packages that are always used together.

### Writing a changeset

A developer adds a changeset alongside their feature:

```bash
pnpm exec changeset add
# Interactive prompt:
# ? Which packages should have a major bump? (none)
# ? Which packages should have a minor bump? @myorg/kv-helpers
# ? Which packages should have a patch bump? @myorg/d1-helpers
# ? Summary: Add `listWithCursor` helper for paginated KV reads
```

This writes `.changeset/fluffy-tiger-123.md`:

```markdown
---
"@myorg/kv-helpers": minor
"@myorg/d1-helpers": patch
---

Add `listWithCursor` helper for paginated KV reads with automatic cursor handling
```

Commit this file alongside the feature:

```bash
git add .changeset/fluffy-tiger-123.md packages/kv-helpers/src/
git commit -m 'feat(kv-helpers): add listWithCursor for paginated KV reads'
```

## Implementation Details

### GitHub Actions — Changesets Release workflow

`.github/workflows/release.yml`:

```yaml
name: Release

on:
  push:
    branches:
      - main

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  release:
    name: Release
    runs-on: ubuntu-latest
    permissions:
      contents: write       # create GitHub releases and push version commits
      id-token: write       # npm provenance
      pull-requests: write  # Changesets PR creation

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # full history for changelog generation

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
          registry-url: https://registry.npmjs.org

      - name: Install dependencies
        run: pnpm install --frozen-lockfile
        env:
          LEFTHOOK: 0

      - name: Build packages
        run: pnpm turbo build --filter="./packages/*"

      - name: Create Release PR or publish
        uses: changesets/action@v1
        with:
          publish: pnpm exec changeset publish
          version: pnpm exec changeset version
          commit: "chore(release): version packages"
          title: "chore(release): version packages"
          createGithubReleases: true
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
          NPM_CONFIG_PROVENANCE: true

  deploy-workers:
    name: Deploy Workers
    needs: release
    runs-on: ubuntu-latest
    if: ${{ needs.release.outputs.published == 'true' }}
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - name: Deploy all Workers
        run: pnpm turbo deploy --filter="./workers/*"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          LEFTHOOK: 0
```

### Package scripts for a publishable npm package

`packages/kv-helpers/package.json`:

```json
{
  "name": "@myorg/kv-helpers",
  "version": "1.2.0",
  "description": "Type-safe Cloudflare KV utilities",
  "type": "module",
  "main": "./dist/index.js",
  "types": "./dist/index.d.ts",
  "exports": {
    ".": {
      "import": "./dist/index.js",
      "types": "./dist/index.d.ts"
    }
  },
  "files": ["dist"],
  "scripts": {
    "build": "tsc -p tsconfig.build.json",
    "test": "vitest run",
    "prepublishOnly": "pnpm run build && pnpm run test"
  },
  "peerDependencies": {
    "@cloudflare/workers-types": ">=4.0.0"
  },
  "devDependencies": {
    "@cloudflare/workers-types": "^4.20240909.0",
    "typescript": "^5.5.0",
    "vitest": "^2.0.0"
  }
}
```

### Example package implementation

```typescript
// packages/kv-helpers/src/index.ts
export interface ListWithCursorOptions {
  prefix?: string;
  limit?: number;
}

export interface PageResult<T> {
  keys: KVNamespaceListKey<T>[];
  cursor: string | null;
  complete: boolean;
}

/**
 * Paginates through KV keys, yielding each page.
 * Automatically handles cursor passing between requests.
 */
export async function* listWithCursor<T = unknown>(
  namespace: KVNamespace,
  options: ListWithCursorOptions = {}
): AsyncGenerator<PageResult<T>> {
  let cursor: string | undefined;
  let complete = false;

  while (!complete) {
    const result = await namespace.list<T>({
      prefix: options.prefix,
      limit: options.limit ?? 1000,
      cursor,
    });

    yield {
      keys: result.keys,
      cursor: result.list_complete ? null : result.cursor,
      complete: result.list_complete,
    };

    if (result.list_complete) {
      complete = true;
    } else {
      cursor = result.cursor;
    }
  }
}

/**
 * Collect all KV keys matching a prefix into an array.
 * Use only for small key spaces — for large spaces use listWithCursor.
 */
export async function listAll<T = unknown>(
  namespace: KVNamespace,
  prefix?: string
): Promise<KVNamespaceListKey<T>[]> {
  const all: KVNamespaceListKey<T>[] = [];
  for await (const page of listWithCursor<T>(namespace, { prefix })) {
    all.push(...page.keys);
  }
  return all;
}
```

### Pre-release tags (beta, alpha, rc)

Enter pre-release mode for a specific channel:

```bash
# Enter pre-release mode
pnpm exec changeset pre enter beta

# Add changesets as normal
pnpm exec changeset add

# Version packages — produces 2.0.0-beta.0
pnpm exec changeset version

# Publish with the beta dist-tag
pnpm exec changeset publish --tag beta

# Exit pre-release mode when ready for stable
pnpm exec changeset pre exit
```

The pre-release mode creates `.changeset/pre.json` tracking the state. Commit this file to allow the pipeline to resume pre-release versioning on subsequent runs.

### GitHub release creation and changelog

The `changesets/action` with `createGithubReleases: true` automatically creates a GitHub release for each published package version, using the content of the generated `CHANGELOG.md` entry as the release body.

`CHANGELOG.md` format after `changeset version`:

```markdown
# @myorg/kv-helpers

## 1.3.0

### Minor Changes

- a1b2c3d: Add `listWithCursor` helper for paginated KV reads with automatic cursor handling
  Thanks @dev-username!

## 1.2.0

### Patch Changes

- Updated dependencies [d4e5f6g]
  - @myorg/d1-helpers@1.2.0
```

### Automated CI check: require changeset for PRs

`.github/workflows/changeset-check.yml`:

```yaml
name: Changeset Check

on:
  pull_request:
    branches: [main]
    paths:
      - 'packages/**'

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - name: Check for changeset
        run: pnpm exec changeset status --since=origin/main --verbose
```

This fails if a PR modifies packages without an accompanying changeset file.

## Anti-patterns

**Do not** run `npm publish` manually from a developer machine. It bypasses the changelog generation, GitHub release creation, and provenance attestation. All publishes must go through the `changesets/action` workflow.

**Do not** commit version bumps directly. The Changesets PR ("Version Packages" PR) should be the only mechanism for version number changes. Committing a manual version bump to `package.json` desynchronises the changelog.

**Do not** use `"commit": true` in `.changeset/config.json` in a CI environment with branch protection rules. This makes the Changesets CLI attempt to commit directly to `main`, which will be rejected by branch protection. The `changesets/action` handles the version commit via its own PR flow.

**Do not** mix Worker deployment versioning with npm package versioning. Workers don't have npm versions — they deploy from source. Only packages in `packages/` should have changesets. Worker deployment should be triggered by the release job's `published` output.

## Gotchas

**The `GITHUB_TOKEN` permissions block is required**. The default `GITHUB_TOKEN` in GitHub Actions does not have `pull-requests: write` permission in organisations with restricted default settings. Without it, the Changesets action cannot create or update the "Version Packages" PR, and silently fails.

**`fetch-depth: 0` on checkout is mandatory**. Changesets compares the current branch to `baseBranch` in git history to find which packages changed. A shallow clone (`fetch-depth: 1`) means the comparison fails and `changeset status` reports zero changes.

**`linked` packages are versioned together but not necessarily published together**. If only one package in a linked group has a changeset, the other will receive a patch bump automatically. Developers sometimes expect a linked package to be skipped entirely — it won't be.

**Pre-release `.changeset/pre.json` must be committed**. If a developer enters pre-release mode locally and doesn't commit `pre.json`, the next run of `changeset version` in CI exits pre-release mode unexpectedly. Always commit `pre.json` changes.

## Verification

```bash
# Check current changeset status
pnpm exec changeset status --verbose

# Dry-run version to see what versions would be bumped
pnpm exec changeset version --snapshot test
# Inspect the temporary version numbers generated
git diff --stat
git checkout .  # revert the dry-run

# Verify the publish script works in isolation
pnpm exec changeset publish --dry-run
# Should list packages that would be published without actually publishing
```

## Related

- `workers-lefthook-git-hooks-monorepo.md` — commit-msg hook enforcing Conventional Commits used in changeset summaries
- `workers-turbo-remote-cache-r2.md` — CI pipeline acceleration that runs before the release job
- `wrangler-config-typescript-types.md` — typed Worker code that ships alongside published packages

## Sources

- https://github.com/changesets/changesets/blob/main/docs/intro-to-using-changesets.md
- https://github.com/changesets/action
- https://docs.npmjs.com/generating-provenance-statements
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
