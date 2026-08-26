# Cloudflare Pages Build Matrix Strategy

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Teams deploying Cloudflare Pages projects that target multiple Node.js versions, support multiple framework adapters, or need to validate builds under different environment variable sets struggle to do this systematically. A change that passes a single build configuration may silently break another variant — for example a Next.js app that works under Node 20 but fails under Node 18 due to a dependency, or a build that succeeds with `NEXT_PUBLIC_ENV=production` but produces an empty bundle with `NEXT_PUBLIC_ENV=staging`.

A Pages build matrix strategy runs multiple build variants in CI before the canonical deploy, ensuring all supported configurations produce a valid, deployable artifact.

## Context

Cloudflare Pages has a single canonical build configuration per project (set in the dashboard or via Wrangler), but CI pipelines are unconstrained. The canonical Pages build runs on Cloudflare's infrastructure; the matrix variants run in GitHub Actions (or your CI provider) using `wrangler pages deploy` with a pre-built `dist/` directory. This means the matrix validates the build step independently of the Pages infrastructure, catching configuration drift before it reaches production.

Pages Functions (`functions/`) are co-located in the repository and compiled as part of the same build; they inherit the same Node version and environment variable matrix, making them natural candidates for matrix coverage.

## Defining the Build Matrix in GitHub Actions

```yaml
# .github/workflows/pages-build-matrix.yml
name: Pages Build Matrix

on:
  pull_request:
  push:
    branches: [main]

jobs:
  build-matrix:
    name: Build (${{ matrix.node }} / ${{ matrix.env_name }})
    runs-on: ubuntu-latest

    strategy:
      fail-fast: false   # run all variants, collect all failures
      matrix:
        node: ["18", "20", "22"]
        env_name: ["staging", "production"]
        include:
          # Add a preview-only variant that skips deploy
          - node: "20"
            env_name: "preview"
            deploy: false
        exclude:
          # Node 18 + production is an unsupported combination in this project
          - node: "18"
            env_name: "production"

    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js ${{ matrix.node }}
        uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node }}
          cache: "npm"

      - name: Install dependencies
        run: npm ci

      - name: Build
        run: npm run build
        env:
          NODE_ENV: ${{ matrix.env_name == 'production' && 'production' || 'development' }}
          NEXT_PUBLIC_ENV: ${{ matrix.env_name }}
          # Inject env-specific secrets from GitHub secrets matrix
          API_BASE_URL: ${{ secrets[format('API_BASE_URL_{0}', toUpper(matrix.env_name))] }}

      - name: Validate build output
        run: node scripts/validate-build.mjs
        env:
          ENV_NAME: ${{ matrix.env_name }}

      - name: Upload build artifact
        uses: actions/upload-artifact@v4
        with:
          name: dist-node${{ matrix.node }}-${{ matrix.env_name }}
          path: .vercel/output/static   # or dist/, out/, etc.
          retention-days: 1

  deploy-canonical:
    name: Deploy (canonical)
    needs: build-matrix
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'

    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js (canonical version)
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - name: Install dependencies
        run: npm ci

      - name: Build for production
        run: npm run build
        env:
          NODE_ENV: production
          NEXT_PUBLIC_ENV: production
          API_BASE_URL: ${{ secrets.API_BASE_URL_PRODUCTION }}

      - name: Deploy to Cloudflare Pages
        run: npx wrangler pages deploy .vercel/output/static --project-name my-pages-project
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
```

## Build Validation Script

A lightweight validator confirms that the output directory contains the expected files and does not have obvious build artifacts missing.

```javascript
// scripts/validate-build.mjs
import { existsSync, statSync, readdirSync } from "fs";
import { resolve } from "path";

const ENV_NAME = process.env.ENV_NAME ?? "production";

const BUILD_DIR = resolve(".vercel/output/static"); // adjust to your framework

function fail(msg) {
  console.error(`[validate-build] FAIL: ${msg}`);
  process.exit(1);
}

function pass(msg) {
  console.log(`[validate-build] OK: ${msg}`);
}

// 1. Build directory must exist and be non-empty
if (!existsSync(BUILD_DIR)) fail(`Build directory not found: ${BUILD_DIR}`);
const entries = readdirSync(BUILD_DIR);
if (entries.length === 0) fail("Build directory is empty");
pass(`Build directory has ${entries.length} entries`);

// 2. index.html must exist
const indexHtml = resolve(BUILD_DIR, "index.html");
if (!existsSync(indexHtml)) fail("index.html missing from build output");
pass("index.html present");

// 3. No placeholder API URLs in JS bundles
import { readFileSync } from "fs";
import { globSync } from "glob";

const jsFiles = globSync(`${BUILD_DIR}/**/*.js`);
for (const file of jsFiles) {
  const content = readFileSync(file, "utf8");
  if (content.includes("localhost:3000") && ENV_NAME === "production") {
    fail(`Found localhost URL in ${file} (production build)`);
  }
}
pass("No localhost URLs found in production JS bundles");

// 4. Total bundle size sanity check (warn only)
let totalBytes = 0;
for (const file of jsFiles) {
  totalBytes += statSync(file).size;
}
const totalMB = (totalBytes / 1024 / 1024).toFixed(2);
if (totalBytes > 50 * 1024 * 1024) {
  console.warn(`[validate-build] WARN: Total JS bundle size ${totalMB} MB exceeds 50 MB`);
} else {
  pass(`Total JS bundle size: ${totalMB} MB`);
}

console.log("[validate-build] All checks passed.");
```

## Framework Adapter Matrix Variant

For projects that support multiple output adapters (e.g. `@astrojs/cloudflare` vs `@astrojs/node`), extend the matrix to cover adapter variants.

```yaml
# Extend the matrix in pages-build-matrix.yml
strategy:
  matrix:
    node: ["20"]
    adapter: ["cloudflare", "node"]
    env_name: ["staging", "production"]

steps:
  - name: Set adapter
    run: |
      # Swap out the astro.config.mjs adapter line
      sed -i "s/adapter: .*/adapter: ${{ matrix.adapter == 'cloudflare' && '@astrojs/cloudflare' || '@astrojs/node' }}/" astro.config.mjs

  - name: Build
    run: npm run build
```

## Pages Functions Compatibility Validation

Pages Functions share the Worker runtime. Add a function-specific smoke test to the matrix that invokes each function route with a test request.

```typescript
// scripts/test-pages-functions.ts
// Run against staging deploy after each matrix build

const BASE_URL = process.env.PAGES_STAGING_URL;
if (!BASE_URL) throw new Error("PAGES_STAGING_URL not set");

const ROUTES = [
  { path: "/api/health", expectedStatus: 200 },
  { path: "/api/user", expectedStatus: 401 }, // unauthenticated
  { path: "/api/missing", expectedStatus: 404 },
];

for (const { path, expectedStatus } of ROUTES) {
  const url = `${BASE_URL}${path}`;
  const resp = await fetch(url);
  if (resp.status !== expectedStatus) {
    console.error(
      `FAIL ${path}: expected ${expectedStatus}, got ${resp.status}`
    );
    process.exit(1);
  }
  console.log(`OK   ${path}: ${resp.status}`);
}
```

## Anti-patterns

- Running only the canonical build in CI and assuming all variants work — a matrix catches configuration-specific failures before they reach production
- Using `fail-fast: true` in the matrix (the default) — a single variant failure cancels all others, hiding unrelated breakage in parallel variants
- Hard-coding the canonical Node version without documenting why other versions are excluded
- Storing env-specific build secrets in repository variables rather than environment-scoped GitHub secrets — all branches can read repository variables
- Deploying all matrix variants to production as separate Pages projects — only the canonical variant should deploy; others are validation-only
- Omitting `retention-days: 1` on matrix build artifacts — CI artifact storage can accumulate quickly across many PRs

## Gotchas

- Cloudflare Pages dashboard build runs in Cloudflare's infrastructure, not your CI runner — a passing CI matrix does not guarantee the dashboard build will succeed if it uses a different Node version or build command
- Pages `_headers` and `_redirects` files are not processed by the build step; they are read at request time by the Pages CDN — matrix builds cannot test redirect/header behavior without an actual Pages deploy
- `wrangler pages deploy` re-deploys even if the build output is identical — use the `--commit-dirty` flag in preview deploys to avoid unnecessary deploys when only test files changed
- Environment variables set in the Pages dashboard are NOT available to CI matrix builds; you must supply them via GitHub Actions secrets
- The `functions/` directory must be co-located with the build output directory in the `wrangler pages deploy` command — pass `--directory` pointing to the dist root, not a subdirectory

## Verification

1. After the matrix workflow runs, check the Actions summary: all variant jobs should be green or have documented exclusions.
2. Download a build artifact from a failing variant (`actions/download-artifact`) and inspect the output directory for missing files or placeholder content.
3. After the canonical deploy, confirm the Pages deployment URL in the Actions output matches the expected branch URL pattern: `https://<branch>.<project>.pages.dev`.
4. Use `wrangler pages deployment list --project-name my-pages-project` to confirm only one deployment exists per commit (not one per matrix variant).

## Related

- `cloudflare-pages-build-cache-optimization.md` — caching node_modules and build outputs between runs
- `cloudflare-pages-preview-deployments.md` — preview deploy strategy for PRs
- `cloudflare-pages-custom-build-config.md` — configuring the canonical build command
- `deploy-artifact-build-parity-ci-gate.md` — ensuring CI artifacts match production builds

## Sources

- Cloudflare Pages: Build configuration: https://developers.cloudflare.com/pages/configuration/build-configuration/
- GitHub Actions: Using a matrix for your jobs: https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/running-variations-of-jobs-in-a-workflow
- Wrangler Pages deploy command: https://developers.cloudflare.com/workers/wrangler/commands/#deploy-1
