# Automated Releases with Release Please for Cloudflare Workers Packages

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A team maintains one or more Cloudflare Workers that are also published as npm packages (e.g., a shared middleware library). The release process is manual:
- Developers forget to bump `package.json` versions
- `CHANGELOG.md` is written by hand and quickly becomes stale
- GitHub Releases are created inconsistently
- Deployments to Cloudflare happen ad-hoc rather than tied to a version tag

The team wants a fully automated pipeline: merge a PR, get a release PR, merge the release PR, get a tagged GitHub Release and an automatic `wrangler deploy`.

---

## Context

Release Please is a Google-maintained GitHub Action that:
1. Parses commit history for Conventional Commits since the last release.
2. Opens a "Release PR" that bumps `package.json`, updates `CHANGELOG.md`, and sets a version tag.
3. On merge of the Release PR, creates a GitHub Release.

For Workers projects the automation chain is:

```
Conventional commit merged to main
  → Release Please opens/updates Release PR
    → Team merges Release PR
      → GitHub Release + version tag created
        → wrangler deploy triggered by on: release
```

Release Please version targeted: **4.x**. Wrangler version targeted: **3.x**.

---

## Solution

### 1. Conventional Commits primer for Workers

```
feat(auth): add HMAC-SHA256 request signing          → minor bump
fix(cache): correct TTL calculation for KV entries   → patch bump
feat!: switch to module syntax Worker                → major bump
chore(deps): update wrangler to 3.65.0               → no bump
docs: update README with wrangler.toml example       → no bump
```

Only `feat`, `fix`, and `BREAKING CHANGE` trigger version bumps.

### 2. release-please-config.json

```json
{
  "$schema": "https://raw.githubusercontent.com/googleapis/release-please/main/schemas/config.json",
  "release-type": "node",
  "packages": {
    ".": {
      "release-type": "node",
      "changelog-sections": [
        { "type": "feat",     "section": "Features" },
        { "type": "fix",      "section": "Bug Fixes" },
        { "type": "perf",     "section": "Performance" },
        { "type": "refactor", "section": "Code Refactoring", "hidden": false },
        { "type": "docs",     "section": "Documentation",    "hidden": true },
        { "type": "chore",    "section": "Miscellaneous",    "hidden": true }
      ],
      "extra-files": [
        {
          "type": "json",
          "path": "wrangler.toml",
          "jsonpath": "$.version"
        }
      ]
    }
  },
  "pull-request-title-pattern": "chore: release ${version}",
  "bump-minor-pre-major": true,
  "bump-patch-for-minor-pre-major": true
}
```

The `extra-files` entry keeps a `version` field in `wrangler.toml` in sync with `package.json`. This is optional but useful for observability dashboards that read the running Worker version.

### 3. .release-please-manifest.json

```json
{
  ".": "1.4.2"
}
```

This file tracks the *current released version* for each package path. Release Please updates it automatically on each release. Commit it to the repository.

### 4. GitHub Actions workflow — release-please

```yaml
# .github/workflows/release-please.yml
name: Release Please

on:
  push:
    branches: [main]

permissions:
  contents: write
  pull-requests: write

jobs:
  release-please:
    runs-on: ubuntu-latest
    outputs:
      release_created: ${{ steps.release.outputs.release_created }}
      tag_name: ${{ steps.release.outputs.tag_name }}
    steps:
      - uses: googleapis/release-please-action@v4
        id: release
        with:
          config-file: release-please-config.json
          manifest-file: .release-please-manifest.json
          token: ${{ secrets.GITHUB_TOKEN }}
```

### 5. GitHub Actions workflow — wrangler deploy after release

```yaml
# .github/workflows/deploy.yml
name: Deploy to Cloudflare Workers

on:
  release:
    types: [published]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm

      - run: npm ci

      - name: Deploy Worker
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          command: deploy --env production
```

The `on: release: types: [published]` trigger fires when Release Please creates the GitHub Release (on merge of the Release PR), not on every push.

### 6. Worker version reporting

```typescript
// src/index.ts
import type { Env } from "./types";
import pkg from "../package.json";

export default {
    async fetch(request: Request, env: Env): Promise<Response> {
        const url = new URL(request.url);

        if (url.pathname === "/__version") {
            return Response.json({
                version: pkg.version,
                name: pkg.name,
                env: env.ENVIRONMENT ?? "unknown",
            });
        }

        return new Response("OK");
    },
} satisfies ExportedHandler<Env>;
```

```jsonc
// tsconfig.json — needed for JSON imports
{
  "compilerOptions": {
    "resolveJsonModule": true
  }
}
```

### 7. Auto-generated CHANGELOG.md (example)

```markdown
## [1.5.0](https://github.com/example-org/example-repo) (2026-08-24)

### Features

* add HMAC-SHA256 request signing ([#42](https://github.com/example-org/example-repo)) ([a1b2c3d](https://github.com/example-org/example-repo))

### Bug Fixes

* correct TTL calculation for KV entries ([#41](https://github.com/example-org/example-repo)) ([d4e5f6a](https://github.com/example-org/example-repo))
```

This is generated automatically by Release Please — do not edit `CHANGELOG.md` by hand.

---

## Implementation Details

### Monorepo support

For a monorepo with multiple Worker packages:

```json
// release-please-config.json
{
  "packages": {
    "packages/worker-api": {
      "release-type": "node",
      "component": "worker-api"
    },
    "packages/worker-cron": {
      "release-type": "node",
      "component": "worker-cron"
    }
  }
}
```

```json
// .release-please-manifest.json
{
  "packages/worker-api": "2.1.0",
  "packages/worker-cron": "1.0.3"
}
```

Each package gets its own Release PR and version tag (e.g., `worker-api-v2.2.0`).

### Squash-merge behaviour

Release Please reads the PR title when commits are squash-merged. Ensure the PR title follows Conventional Commits format, or set `merge-commit-title` in the GitHub repo settings and train contributors accordingly.

---

## Anti-patterns

- **Manually editing `CHANGELOG.md`.** Release Please will clobber manual edits on the next run. All changelog content must come from commit messages.
- **Merging Release PRs before tests pass.** Add a branch protection rule that requires the CI workflow to pass on Release PRs. Release Please respects branch protection.
- **Using `secrets.GITHUB_TOKEN` for `wrangler deploy`.** The deploy workflow needs `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` stored as repository secrets, not the GitHub token.
- **Running `wrangler deploy` on every push to main.** Tie deploys to releases. Deploying on every commit to main means untested intermediary states reach production.

---

## Gotchas

- Release Please opens one Release PR per package. If many features land in quick succession, the PR is updated (not duplicated). Do not close Release PRs manually — Release Please will reopen them.
- The `bump-minor-pre-major` flag prevents `feat` commits from bumping the major version when the current version is `0.x`. This is important for pre-1.0 Workers.
- `wrangler.toml` uses TOML format. The `extra-files` JSON path support for TOML is limited to top-level string fields. Nested tables require a custom `extra-files` type of `generic` with a regex pattern.
- If the `GITHUB_TOKEN` lacks `pull-requests: write` permission (common in fork PRs), Release Please silently does nothing. Check workflow permissions at the job level.

---

## Verification

```bash
# Simulate what Release Please would generate (dry-run via CLI)
npx release-please release-pr \
  --repo-url=example-org/example-repo \
  --token=$GITHUB_TOKEN \
  --config-file=release-please-config.json \
  --manifest-file=.release-please-manifest.json \
  --dry-run

# Verify the current manifest version
cat .release-please-manifest.json

# Confirm wrangler deploy works independently
npx wrangler deploy --env production --dry-run
```

---

## Related

- `documentation/docs/policies/devtools/workers-dependabot-wrangler-updates.md`
- `documentation/docs/policies/devtools/workers-knip-dead-code-elimination.md`
- `documentation/ci/workers-github-actions-deploy.md`

---

## Sources

- https://github.com/googleapis/release-please
- https://github.com/googleapis/release-please-action
- https://www.conventionalcommits.org/en/v1.0.0/
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://github.com/cloudflare/wrangler-action
