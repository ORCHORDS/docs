# Cloudflare Pages Custom Build Output: `_headers`, `_redirects`, `_routes.json`, Functions Exclusions, and Direct Upload

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Pages site needs custom HTTP response headers (CSP, CORS, cache-control), URL redirects, fine-grained control over which routes invoke Pages Functions vs. serve static assets, and a CI pipeline that uploads the build output directly rather than triggering a Git-connected build. This article covers all four special output files and the direct upload workflow.

## Context

- Cloudflare Pages (free and paid tiers)
- `_headers`, `_redirects`, `_routes.json` are placed in the build output directory (e.g. `dist/` or `public/`)
- Pages Functions live in a `functions/` directory at the repo root (not inside `dist/`)
- Direct upload via Wrangler CLI (`wrangler pages deploy`) or REST API for CI without Git integration
- Stack: TypeScript Pages Functions, Wrangler v3, bash CI scripts

---

## Section 1: `_headers` — Custom HTTP Response Headers

The `_headers` file controls response headers per URL pattern. Place it in your build output directory.

```text
# dist/_headers

# Apply to all routes
/*
  X-Frame-Options: DENY
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()

# Strict CSP for HTML pages
/
  Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.example.com; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' https://api.example.com; frame-ancestors 'none'

# Long-lived cache for hashed static assets
/assets/*
  Cache-Control: public, max-age=31536000, immutable

# No cache for HTML
/*.html
  Cache-Control: public, max-age=0, must-revalidate

# CORS for API responses served from Pages Functions
/api/*
  Access-Control-Allow-Origin: https://app.example.com
  Access-Control-Allow-Methods: GET, POST, OPTIONS
  Access-Control-Allow-Headers: Content-Type, Authorization
  Access-Control-Max-Age: 86400
```

---

## Section 2: `_redirects` — URL Redirects and Rewrites

```text
# dist/_redirects
# Format: <source> <destination> [status code] [conditions]
# Max 2000 rules. Processed top-to-bottom; first match wins.

# Permanent redirect for old blog paths
/blog/old-post-slug /blog/new-post-slug 301

# Temporary redirect during maintenance
# /maintenance/* /maintenance.html 302

# SPA fallback — serve index.html for all unmatched paths (must come last)
# Note: prefer _routes.json for SPAs to avoid invoking Functions on static files
/app/* /app/index.html 200

# Country-based redirect (Cloudflare geo variable)
/pricing /pricing-eu 302 Country=DE,FR,AT,CH
/pricing /pricing-uk 302 Country=GB

# Force HTTPS (usually handled by Cloudflare automatically; only needed for custom domains)
# http://example.com/* https://example.com/:splat 301

# Proxy/rewrite to external origin (Pages rewrites, not proxy — destination must be same hostname)
# /legacy/* /v1/:splat 200
```

---

## Section 3: `_routes.json` — Control Static vs. Functions Routing

`_routes.json` tells Pages which paths should invoke Functions and which should serve static files directly. This is critical for performance — running a Function for every static asset request wastes CPU.

```json
{
  "version": 1,
  "include": [
    "/api/*",
    "/auth/*",
    "/webhooks/*"
  ],
  "exclude": [
    "/assets/*",
    "/images/*",
    "/*.ico",
    "/*.txt",
    "/*.xml",
    "/*.json",
    "/*.webmanifest"
  ]
}
```

```typescript
// functions/api/users/[id].ts
// Matched by _routes.json include: /api/*

import type { EventContext } from "@cloudflare/workers-types";

interface Env {
  DB: D1Database;
}

export async function onRequestGet(
  context: EventContext<Env, "id", Record<string, string>>
): Promise<Response> {
  const { id } = context.params;
  const user = await context.env.DB
    .prepare("SELECT id, name, email FROM users WHERE id = ?")
    .bind(id)
    .first();

  if (!user) {
    return Response.json({ error: "User not found" }, { status: 404 });
  }

  return Response.json(user);
}

export async function onRequestOptions(): Promise<Response> {
  // CORS preflight — headers added by _headers file above
  return new Response(null, { status: 204 });
}
```

---

## Section 4: Pages Direct Upload for CI

Direct upload decouples your build from Cloudflare's Git integration, enabling custom CI pipelines (GitHub Actions, GitLab CI, Bitbucket).

```bash
#!/usr/bin/env bash
# scripts/deploy-pages.sh
# Usage: CF_ACCOUNT_ID=xxx CF_API_TOKEN=xxx ./scripts/deploy-pages.sh

set -euo pipefail

PROJECT_NAME="my-pages-project"
BUILD_DIR="dist"
BRANCH="${GITHUB_REF_NAME:-main}"
COMMIT_SHA="${GITHUB_SHA:-$(git rev-parse HEAD)}"

# Build the project
npm ci
npm run build

# Deploy via Wrangler direct upload
npx wrangler pages deploy "${BUILD_DIR}" \
  --project-name="${PROJECT_NAME}" \
  --branch="${BRANCH}" \
  --commit-hash="${COMMIT_SHA}" \
  --commit-message="$(git log -1 --pretty=%s)"

echo "Deployed to Cloudflare Pages successfully."
```

```yaml
# .github/workflows/deploy.yml
name: Deploy to Cloudflare Pages

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      deployments: write
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - name: Install dependencies
        run: npm ci

      - name: Build
        run: npm run build

      - name: Deploy to Cloudflare Pages
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          npx wrangler pages deploy dist \
            --project-name=my-pages-project \
            --branch=${{ github.ref_name }} \
            --commit-hash=${{ github.sha }}
```

---

## Section 5: Create a Pages Project via API (First-Time Setup)

```bash
# Create the Pages project (one-time)
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/pages/projects" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-pages-project",
    "production_branch": "main"
  }' | jq '.result | {name, subdomain, id}'

# Add a D1 binding to the project (for Functions)
curl -s -X PATCH \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/pages/projects/my-pages-project" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "deployment_configs": {
      "production": {
        "d1_databases": {
          "DB": { "id": "<d1-database-id>" }
        }
      }
    }
  }' | jq .
```

---

## Anti-patterns

- Do not place `_headers`, `_redirects`, or `_routes.json` in the repo root — they must be inside the build output directory.
- Do not use `_redirects` for SPA routing without excluding static asset paths first in `_routes.json` — this triggers unnecessary Function invocations.
- Do not set `Cache-Control: max-age=31536000` on HTML files — browsers will cache stale HTML until expiry; only use immutable cache on content-hashed assets.
- Do not use direct upload for large teams without a project-level API token; prefer scoped tokens per project.
- Do not exceed 2000 rules in `_redirects` — the file is silently truncated at the limit.

## Gotchas

- `_routes.json` `include`/`exclude` rules use glob matching, not regex; `**` is not supported — use `/*` for subtree matching.
- Headers set in `_headers` do not override headers set by Pages Functions; Functions take precedence.
- The `200` status code in `_redirects` is a rewrite (no browser redirect), but only works for same-site paths.
- `wrangler pages deploy` without `--branch` defaults to `main`; preview deployments require a non-production branch name.
- D1 bindings configured via the API take effect on the next deployment, not immediately.
- Pages Functions in `functions/` are compiled separately from static assets; changes to `functions/` require a full redeploy even if `dist/` did not change.

## Verification

```bash
# Check deployed headers
curl -sI https://my-pages-project.pages.dev/ | grep -E "(content-security|x-frame|cache-control)"

# Test redirect
curl -sI https://my-pages-project.pages.dev/blog/old-post-slug | grep location

# List deployments
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/pages/projects/my-pages-project/deployments" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[0] | {id, url, created_on, stage: .stages[-1].name}'

# Tail Pages Function logs
npx wrangler pages deployment tail --project-name=my-pages-project
```

## Related

- `documentation/categories/infra/workers-for-platforms-dispatch-namespace.md`
- `documentation/categories/infra/cloudflare-ddos-managed-ruleset-workers-api.md`

## Sources

- https://developers.cloudflare.com/pages/configuration/headers/
- https://developers.cloudflare.com/pages/configuration/redirects/
- https://developers.cloudflare.com/pages/functions/routing/
- https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/
- https://developers.cloudflare.com/pages/functions/bindings/
