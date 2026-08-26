# Semantic Versioning for Cloudflare Workers APIs with Breaking Change Detection

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

---

## Symptom / Use-case

A Cloudflare Workers-based API is consumed by mobile apps, third-party integrations, and
other internal Workers. A developer renames a response field, removes an optional parameter,
or tightens a validation rule without realizing these are breaking changes for callers.
The existing CI pipeline deploys successfully, but downstream consumers break in production.
You need an automated gate that detects breaking changes in the API contract before merge,
enforces a version bump when they are detected, and blocks deploys until versioning and
changelog entries are correct.

---

## Context

Cloudflare Workers that expose HTTP APIs can be versioned in two primary ways:

1. **URL-path versioning** (`/v1/`, `/v2/`) — hard boundary, easy to route with Workers
   routing rules.
2. **Header versioning** (`API-Version: 2026-08-01`) — date-based, used by Stripe-style
   APIs; each Worker inspects the header and responds accordingly.

Either approach requires automated detection of breaking changes so that the correct version
bump is applied before a PR merges. The OpenAPI specification (OAS 3.x) stored in the
repository is the source of truth. Tools like `oasdiff` or `openapi-diff` can compare the
current spec against the spec on `main` and classify changes as `BREAKING`, `NON_BREAKING`,
or `INFO`.

The workflow:
1. PR opens or updates.
2. CI extracts the OpenAPI spec from the Workers codebase (or a committed spec file).
3. CI fetches the spec from `main`.
4. `oasdiff` compares the two; results are annotated onto the PR.
5. If breaking changes are found, the workflow checks that the PR includes a semver `major`
   bump in the relevant `package.json` / `wrangler.toml` version field and a
   `BREAKING CHANGE:` footer in at least one commit message.
6. If either is missing, the workflow fails and blocks the merge.

---

## Storing and Generating the OpenAPI Spec

For a Hono-based Worker the spec can be auto-generated from route definitions:

```ts
// src/openapi.ts
import { OpenAPIHono } from '@hono/zod-openapi'
import { writeFileSync } from 'node:fs'

const app = new OpenAPIHono()

// Register routes with Zod schemas …

// Export spec for CI
export const generateSpec = () =>
  app.getOpenAPI31Document({
    openapi: '3.1.0',
    info: { title: 'Orchords API', version: process.env.API_VERSION ?? '0.0.0' },
  })

// CLI entrypoint: `node -e "require('./src/openapi').generateSpec()" > openapi.json`
if (process.argv[1] === new URL(import.meta.url).pathname) {
  writeFileSync('openapi.json', JSON.stringify(generateSpec(), null, 2))
  console.log('openapi.json written')
}
```

Commit the generated `openapi.json` to the repository root (or a `specs/` directory).
The CI workflow regenerates it from source during the check so drift is caught immediately.

---

## Breaking Change Detection with `oasdiff`

`oasdiff` is a Go binary available as a Docker image and GitHub Action. It understands
the OpenAPI 3.x semantics of breaking vs. non-breaking changes.

```bash
# Install (Linux)
curl -sSL https://raw.githubusercontent.com/tufin/oasdiff/main/install.sh | bash

# Compare base (main) against head (PR branch)
oasdiff breaking base-openapi.json head-openapi.json \
  --format=text \
  --fail-on=ERR   # exit code 1 on BREAKING changes
```

Common breaking changes detected:

| Change | Classification |
|--------|---------------|
| Remove a required request parameter | BREAKING |
| Remove a response property | BREAKING |
| Add a required request body property | BREAKING |
| Change a property type (`string` → `integer`) | BREAKING |
| Narrow an enum (remove a valid value) | BREAKING |
| Add an optional response property | NON_BREAKING |
| Add an optional query parameter | NON_BREAKING |
| Change a description | INFO |

---

## CI Workflow

```yaml
# .github/workflows/api-breaking-change.yml
name: API Breaking Change Detection

on:
  pull_request:
    branches: [main, production]
    paths:
      - 'src/**'
      - 'openapi.json'
      - 'package.json'

permissions:
  contents: read
  pull-requests: write

jobs:
  detect-breaking-changes:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout PR branch
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - name: Install dependencies
        run: pnpm install --frozen-lockfile

      - name: Generate OpenAPI spec from PR branch
        run: pnpm exec tsx src/openapi.ts > openapi-head.json

      - name: Fetch OpenAPI spec from main
        run: |
          git show origin/main:openapi.json > openapi-base.json 2>/dev/null || \
            echo '{"openapi":"3.1.0","info":{"title":"","version":"0.0.0"},"paths":{}}' \
            > openapi-base.json

      - name: Install oasdiff
        run: |
          curl -sSL \
            https://github.com/tufin/oasdiff/releases/latest/download/oasdiff_linux_amd64.tar.gz \
            | tar -xz -C /usr/local/bin oasdiff
          chmod +x /usr/local/bin/oasdiff

      - name: Run breaking change check
        id: breaking
        run: |
          set +e
          RESULT=$(oasdiff breaking openapi-base.json openapi-head.json --format=text 2>&1)
          EXIT_CODE=$?
          echo "result<<EOF" >> "$GITHUB_OUTPUT"
          echo "$RESULT"     >> "$GITHUB_OUTPUT"
          echo "EOF"         >> "$GITHUB_OUTPUT"
          echo "exit_code=$EXIT_CODE" >> "$GITHUB_OUTPUT"
          set -e

      - name: Extract version from package.json
        id: versions
        run: |
          HEAD_VERSION=$(node -p "require('./package.json').version")
          BASE_VERSION=$(git show origin/main:package.json | node -p \
            "JSON.parse(require('fs').readFileSync('/dev/stdin','utf8')).version" || echo "0.0.0")
          echo "head=$HEAD_VERSION" >> "$GITHUB_OUTPUT"
          echo "base=$BASE_VERSION" >> "$GITHUB_OUTPUT"

      - name: Check semver bump on breaking changes
        id: semver_check
        if: steps.breaking.outputs.exit_code != '0'
        run: |
          HEAD="${{ steps.versions.outputs.head }}"
          BASE="${{ steps.versions.outputs.base }}"

          HEAD_MAJOR=$(echo "$HEAD" | cut -d. -f1)
          BASE_MAJOR=$(echo "$BASE" | cut -d. -f1)

          if [[ "$HEAD_MAJOR" -le "$BASE_MAJOR" ]]; then
            echo "bump_missing=true" >> "$GITHUB_OUTPUT"
          else
            echo "bump_missing=false" >> "$GITHUB_OUTPUT"
          fi

      - name: Check BREAKING CHANGE commit footer
        id: commit_check
        if: steps.breaking.outputs.exit_code != '0'
        run: |
          if git log origin/main..HEAD --format='%B' | grep -q "^BREAKING CHANGE:"; then
            echo "footer_missing=false" >> "$GITHUB_OUTPUT"
          else
            echo "footer_missing=true" >> "$GITHUB_OUTPUT"
          fi

      - name: Post PR comment
        uses: actions/github-script@v7
        with:
          script: |
            const breaking    = `${{ steps.breaking.outputs.result }}`;
            const exitCode    = `${{ steps.breaking.outputs.exit_code }}`;
            const bumpMissing = `${{ steps.semver_check.outputs.bump_missing }}`;
            const footerMissing = `${{ steps.commit_check.outputs.footer_missing }}`;

            if (exitCode === '0') {
              await github.rest.issues.createComment({
                ...context.repo,
                issue_number: context.payload.pull_request.number,
                body: '**API Breaking Change Check**: no breaking changes detected.',
              });
              return;
            }

            let body = `## Breaking Changes Detected\n\n\`\`\`\n${breaking}\n\`\`\`\n\n`;

            if (bumpMissing === 'true') {
              body += `**Major version bump missing** — increment the major version in \`package.json\`.\n`;
            }
            if (footerMissing === 'true') {
              body += `**Commit footer missing** — add \`BREAKING CHANGE: <description>\` to at least one commit message.\n`;
            }

            await github.rest.issues.createComment({
              ...context.repo,
              issue_number: context.payload.pull_request.number,
              body,
            });

      - name: Fail on unacknowledged breaking changes
        if: |
          steps.breaking.outputs.exit_code != '0' &&
          (steps.semver_check.outputs.bump_missing == 'true' ||
           steps.commit_check.outputs.footer_missing == 'true')
        run: |
          echo "Breaking changes detected without required version bump or commit footer."
          exit 1
```

---

## Version Field in `wrangler.toml`

For Workers that don't use `package.json` as the version authority, store the API version
in `wrangler.toml` as a variable:

```toml
# wrangler.toml
[vars]
API_VERSION = "2.0.0"
```

Read it in the Worker:

```ts
// src/index.ts
export default {
  fetch(request: Request, env: Env) {
    const apiVersion = env.API_VERSION   // injected at deploy time
    // Route based on 'API-Version' header or URL prefix
  }
}
```

The CI version-check step becomes:

```bash
HEAD_VERSION=$(grep 'API_VERSION' wrangler.toml | head -1 | sed 's/.*= *"\(.*\)"/\1/')
BASE_VERSION=$(git show origin/main:wrangler.toml | grep 'API_VERSION' | head -1 | \
  sed 's/.*= *"\(.*\)"/\1/')
```

---

## Deprecation Marking Before Removal

Breaking removals should follow a deprecation window. Use the OpenAPI `deprecated` flag:

```json
{
  "paths": {
    "/v1/tracks": {
      "get": {
        "deprecated": true,
        "description": "Deprecated: use /v2/tracks instead. Will be removed 2026-12-01.",
        "x-sunset": "2026-12-01"
      }
    }
  }
}
```

The CI workflow can warn on `deprecated` paths still present after their `x-sunset` date:

```bash
TODAY=$(date +%Y-%m-%d)
jq -r '.paths | to_entries[] |
  select(.value | to_entries[] | select(.value.deprecated == true and
    (.value["x-sunset"] // "9999-99-99") < env.TODAY)) |
  "\(.key) has passed its sunset date"' openapi-head.json
```

---

## Anti-patterns

- **Trusting only unit tests**: Unit tests do not catch contract drift between the spec and
  the implementation. Always regenerate the spec from source and diff it.
- **Versioning the entire Worker instead of the API resource**: A single Worker may expose
  multiple API namespaces. Version each namespace independently; bumping the entire Worker
  version for an unrelated route change creates unnecessary consumer churn.
- **Removing a deprecated endpoint in the same PR that adds `deprecated: true`**: Always
  ship the deprecation flag in one release, wait one or more release cycles, then remove.
- **Treating renamed fields as non-breaking**: Renaming `trackId` to `track_id` is a
  breaking change for JSON consumers even if the data is identical.

---

## Gotchas

- **`oasdiff` false positives on enum extensions**: Adding a new enum value to a *response*
  field is technically non-breaking (callers should handle unknown values), but `oasdiff`
  may flag it. Use `--exclude-elements=response-enum-value-added` to suppress.
- **Spec generation depends on build environment**: If the spec-generation script reads
  `process.env.API_VERSION`, the CI must set it explicitly or the version comparison will
  always show `0.0.0` vs. `0.0.0`.
- **OpenAPI 3.1 vs 3.0 differences**: `oasdiff` handles both but the `nullable` keyword
  behaves differently. Standardize on 3.1 across the team.
- **Workers deployed to multiple environments (dev/staging/production)**: The version in
  `wrangler.toml` may vary per environment via `[env.production]` overrides. The CI check
  should target the `[vars]` block, not an environment-specific override.

---

## Verification

```bash
# Manual diff between current branch and main
git stash
git show main:openapi.json > /tmp/base.json
git stash pop
pnpm exec tsx src/openapi.ts > /tmp/head.json
oasdiff breaking /tmp/base.json /tmp/head.json

# Verify semver format in package.json
node -e "const s=require('./package.json').version;
  if(!/^\d+\.\d+\.\d+$/.test(s)){process.exit(1);}
  console.log('Version OK:', s)"

# Confirm BREAKING CHANGE footer exists
git log origin/main..HEAD --format='%B' | grep 'BREAKING CHANGE:'
```

---

## Related

- `semantic-versioning-2026.md` — general semver policy and tooling
- `conventional-commits-2026.md` — commit message format and BREAKING CHANGE footer
- `github-actions-wrangler-deploy-pipeline.md` — Workers deploy pipeline integration
- `openapi-api-documentation.md` — generating and hosting OpenAPI docs

---

## Sources

- `oasdiff` — https://github.com/tufin/oasdiff
- OpenAPI 3.1 specification — https://spec.openapis.org/oas/v3.1.0
- Hono `@hono/zod-openapi` — https://hono.dev/snippets/zod-openapi
- Cloudflare Workers `wrangler.toml` vars — https://developers.cloudflare.com/workers/wrangler/configuration/
- Semantic Versioning 2.0.0 — https://semver.org
