# Semantic Versioning Automation for Workers Packages

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Shared packages (`@example-org/example-repo`, `@example-org/example-repo`) have no consistent versioning — developers bump versions manually, forget to update CHANGELOG.md, and tag releases inconsistently. Meanwhile, the Worker itself has no version tracking: support cannot tell which version is live in production. You need automated version bumps driven by commit history, automatic changelog generation, and version metadata written to D1.

## Context

`semantic-release` analyzes conventional commits since the last release tag, determines the next semver version (patch/minor/major), writes CHANGELOG.md, creates a git tag, publishes to npm (for public packages), and can execute arbitrary release steps (deploying the Worker, writing version to D1) via plugins. The tool runs in CI on merge to `main` and is entirely non-interactive.

For Cloudflare Workers the release pipeline is: analyze commits → bump version → generate changelog → tag → (optionally publish to npm) → deploy Worker → record version in D1.

## Solution

**Install semantic-release and plugins:**

```bash
npm install --save-dev \
  semantic-release \
  @semantic-release/changelog \
  @semantic-release/git \
  @semantic-release/github \
  @semantic-release/npm \
  @semantic-release/exec
```

**`.releaserc.json`** for a shared package (`@example-org/example-repo`):

```json
{
  "branches": [
    "main",
    { "name": "beta", "prerelease": true },
    { "name": "release/*", "prerelease": "rc" }
  ],
  "plugins": [
    "@semantic-release/commit-analyzer",
    "@semantic-release/release-notes-generator",
    [
      "@semantic-release/changelog",
      {
        "changelogFile": "CHANGELOG.md"
      }
    ],
    [
      "@semantic-release/npm",
      {
        "npmPublish": true,
        "pkgRoot": "."
      }
    ],
    [
      "@semantic-release/git",
      {
        "assets": ["CHANGELOG.md", "package.json"],
        "message": "chore(release): ${nextRelease.version} [skip ci]\n\n${nextRelease.notes}"
      }
    ],
    "@semantic-release/github"
  ]
}
```

**`.releaserc.json`** for a Cloudflare Worker (no npm publish, deploy + D1 version record):

```json
{
  "branches": ["main"],
  "tagFormat": "api-gateway@${version}",
  "plugins": [
    "@semantic-release/commit-analyzer",
    "@semantic-release/release-notes-generator",
    [
      "@semantic-release/changelog",
      {
        "changelogFile": "CHANGELOG.md"
      }
    ],
    [
      "@semantic-release/npm",
      {
        "npmPublish": false
      }
    ],
    [
      "@semantic-release/exec",
      {
        "publishCmd": "./scripts/deploy-and-record.sh ${nextRelease.version}"
      }
    ],
    [
      "@semantic-release/git",
      {
        "assets": ["CHANGELOG.md", "package.json"],
        "message": "chore(release): api-gateway@${nextRelease.version} [skip ci]"
      }
    ],
    "@semantic-release/github"
  ]
}
```

**`scripts/deploy-and-record.sh`** — deploy Worker and write version to D1:

```bash
#!/usr/bin/env bash
set -euo pipefail

VERSION="$1"
WORKER_NAME="orchords-api-gateway"
DEPLOYED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
COMMIT_SHA=$(git rev-parse HEAD)

echo "Deploying $WORKER_NAME version $VERSION (commit: $COMMIT_SHA)"

# Deploy the Worker
npx wrangler deploy --name "$WORKER_NAME"

# Record the version in D1 for runtime introspection
npx wrangler d1 execute orchords-prod \
  --command "INSERT INTO worker_releases (worker_name, version, commit_sha, deployed_at)
             VALUES ('$WORKER_NAME', '$VERSION', '$COMMIT_SHA', '$DEPLOYED_AT')"

echo "Recorded release: $VERSION at $DEPLOYED_AT"
```

**D1 migration to create the releases table:**

```sql
-- migrations/0010_worker_releases.sql
CREATE TABLE IF NOT EXISTS worker_releases (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  worker_name TEXT    NOT NULL,
  version     TEXT    NOT NULL,
  commit_sha  TEXT    NOT NULL,
  deployed_at TEXT    NOT NULL,
  created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_worker_releases_name_deployed
  ON worker_releases (worker_name, deployed_at DESC);
```

**Version endpoint in the Worker:**

```typescript
import type { WorkerEnv } from '@example-org/example-repo';

interface Release {
  version: string;
  commit_sha: string;
  deployed_at: string;
}

async function handleVersionRequest(env: WorkerEnv): Promise<Response> {
  const result = await env.DB.prepare(
    `SELECT version, commit_sha, deployed_at
     FROM worker_releases
     WHERE worker_name = 'orchords-api-gateway'
     ORDER BY deployed_at DESC
     LIMIT 1`
  ).first<Release>();

  if (!result) {
    return new Response(JSON.stringify({ version: 'unknown' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  return new Response(
    JSON.stringify({
      version: result.version,
      commitSha: result.commit_sha,
      deployedAt: result.deployed_at,
    }),
    {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }
  );
}

export default {
  async fetch(request: Request, env: WorkerEnv, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === '/_version') {
      return handleVersionRequest(env);
    }
    // ... rest of routing
    return new Response('Not Found', { status: 404 });
  },
};
```

**GitHub Actions workflow (`.github/workflows/release.yml`):**

```yaml
name: Release

on:
  push:
    branches:
      - main

jobs:
  release:
    name: Semantic Release
    runs-on: ubuntu-latest
    permissions:
      contents: write
      issues: write
      pull-requests: write
      id-token: write

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          persist-credentials: false

      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'npm'

      - run: npm ci

      - name: Release
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          NPM_TOKEN: ${{ secrets.NPM_TOKEN }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
        run: npx semantic-release
```

**Monorepo variant — per-package release with `multi-semantic-release`:**

```bash
npm install --save-dev multi-semantic-release
```

```json
{
  "scripts": {
    "release": "multi-semantic-release"
  }
}
```

`multi-semantic-release` reads `.releaserc.json` from each workspace package and runs semantic-release independently for each, respecting topological order (dependencies release before dependents).

## Implementation Details

- `semantic-release` relies on `fetch-depth: 0` in the checkout step — it needs the full git history to find the previous release tag and compute the changelog. Shallow clones (`--depth 1`, the default) will cause it to fail or compute an incorrect version.
- The `[skip ci]` suffix in the release commit message prevents GitHub Actions from re-triggering the release workflow on the commit that semantic-release pushes back to `main`.
- `tagFormat: "api-gateway@${version}"` scopes tags to the worker. Without this, multiple workers in the same repo would share a tag namespace and overwrite each other's releases.
- The `@semantic-release/exec` `publishCmd` receives the computed `nextRelease.version` as a shell argument. Other available variables: `${nextRelease.gitTag}`, `${nextRelease.notes}`, `${lastRelease.version}`.
- `"npmPublish": false` in the Worker's config prevents semantic-release from attempting to publish the Worker package to the npm registry (Workers are not published to npm).

## Anti-patterns

- **Manual `npm version` calls**: Bypasses the commit analysis, breaking the CHANGELOG continuity and potentially double-tagging.
- **Releasing from feature branches**: semantic-release should only run on `main` (and explicitly configured prerelease branches). Triggering it on PRs will create unwanted prerelease tags.
- **Not setting `persist-credentials: false`**: Without this, the `GITHUB_TOKEN` baked into the checkout credential will not have write permission for pushing the release commit back. Use a PAT or GitHub App token with `contents: write`.
- **Embedding `$VERSION` in wrangler.toml**: The version should live in `package.json` (managed by semantic-release) and be read dynamically. Hardcoding it in `wrangler.toml` creates a second source of truth that drifts.

## Gotchas

- If the last commit on `main` is already a `[skip ci]` release commit (e.g., after a force push or rebase), semantic-release will find no new commits and produce no release — this is correct behaviour, not a bug.
- `multi-semantic-release` does not support all plugins that `semantic-release` supports. Verify plugin compatibility before adopting it in a monorepo.
- The D1 `INSERT` in `deploy-and-record.sh` uses string interpolation. For production use, switch to Wrangler's `--json` flag with parameterised queries or use the D1 REST API with proper escaping to avoid SQL injection from version strings containing special characters.
- `@semantic-release/github` creates GitHub Releases. If you do not want public GitHub Release notes (e.g., for internal monorepo packages), omit this plugin or configure `successComment: false`.

## Verification

```bash
# Dry-run to see what version would be released without making changes
npx semantic-release --dry-run --no-ci

# Inspect what commits would be analyzed
git log $(git describe --tags --abbrev=0)..HEAD --oneline

# Verify the D1 release record after deploy
npx wrangler d1 execute orchords-prod \
  --command "SELECT * FROM worker_releases ORDER BY deployed_at DESC LIMIT 5"

# Check the version endpoint in production
curl https://api.example.com/_version
# {"version":"2.4.1","commitSha":"abc1234","deployedAt":"2026-08-24T12:00:00Z"}
```

## Related

- `conventional-commits-enforcement.md` — commit format required for version analysis
- `workers-monorepo-turborepo-setup.md` — monorepo context for multi-package releases
- `workers-dependency-update-workflow.md` — Renovate auto-merges interact with release tags
- `release-branch-strategy.md` — how prerelease branches map to `beta` and `rc` config

## Sources

- https://semantic-release.gitbook.io/semantic-release/
- https://github.com/semantic-release/semantic-release
- https://github.com/dhoulb/multi-semantic-release
- https://developers.cloudflare.com/d1/wrangler-commands/
