# GitHub Actions – Wrangler Pages Functions Deploy Pipeline

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You have a Cloudflare Pages project that includes Pages Functions (TypeScript files under
`functions/`) and a `wrangler.toml`. Using the Pages GitHub integration or a bare
`wrangler pages publish` does not pick up KV/D1/R2 bindings declared in `wrangler.toml`,
and compatibility flags set in the dashboard do not match what your CI pipeline deploys.
You need a reproducible, config-driven pipeline that builds, validates, and deploys Pages
Functions with the same binding declarations that production uses.

## Context

Cloudflare Pages Functions are full Workers running inside a Pages project. Since
Wrangler 3.x, `wrangler pages deploy` (replacing the deprecated `wrangler pages publish`)
reads a `wrangler.toml` at the project root when one is present, making bindings,
compatibility dates, and route declarations first-class CI concerns rather than dashboard
state. The pipeline described here pins wrangler, validates function types, runs
`pages:dev` smoke tests, and promotes through preview → production with manual approval
gating the production leg.

## 1. Repository Layout

```
my-pages-app/
├── functions/
│   ├── api/
│   │   └── hello.ts          # Pages Function: GET /api/hello
│   ├── _middleware.ts         # Global middleware
│   └── _routes.json          # Opt-in route matching
├── public/                   # Static assets
├── wrangler.toml
└── package.json
```

`wrangler.toml` for a Pages project with bindings:

```toml
name = "my-pages-app"
pages_build_output_dir = "public"
compatibility_date = "2026-06-01"
compatibility_flags = ["nodejs_compat"]

[[kv_namespaces]]
binding = "SESSIONS"
id = "abc123"

[[d1_databases]]
binding = "DB"
database_name = "prod-db"
database_id = "def456"

[env.preview]
[[env.preview.kv_namespaces]]
binding = "SESSIONS"
id = "xyz789"
[[env.preview.d1_databases]]
binding = "DB"
database_name = "preview-db"
database_id = "ghi012"
```

## 2. Typed Pages Function with Bindings

```typescript
// functions/api/hello.ts
interface Env {
  SESSIONS: KVNamespace;
  DB: D1Database;
}

export const onRequestGet: PagesFunction<Env> = async (context) => {
  const { env, request } = context;

  const sessionId = request.headers.get("x-session-id");
  if (!sessionId) {
    return new Response(JSON.stringify({ error: "missing session" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  const session = await env.SESSIONS.get(sessionId, { type: "json" });
  if (!session) {
    return new Response(JSON.stringify({ error: "session not found" }), {
      status: 404,
      headers: { "Content-Type": "application/json" },
    });
  }

  const { results } = await env.DB.prepare(
    "SELECT greeting FROM config WHERE active = 1 LIMIT 1"
  ).all<{ greeting: string }>();

  return Response.json({ greeting: results[0]?.greeting ?? "hello", session });
};
```

## 3. GitHub Actions Workflow

```yaml
# .github/workflows/pages-functions-deploy.yml
name: Pages Functions Deploy

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

concurrency:
  group: pages-deploy-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

jobs:
  build-and-type-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - run: npm ci

      # Type-check functions against the Workers types package
      - run: npx tsc --noEmit --project tsconfig.functions.json

      # Build static assets
      - run: npm run build

      - uses: actions/upload-artifact@v4
        with:
          name: pages-build-${{ github.sha }}
          path: public/
          retention-days: 3

  deploy-preview:
    needs: build-and-type-check
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    environment: preview
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4

      - uses: actions/download-artifact@v4
        with:
          name: pages-build-${{ github.sha }}
          path: public/

      - name: Deploy to Pages preview
        id: deploy
        run: |
          npx wrangler@3 pages deploy public \
            --project-name "${{ vars.PAGES_PROJECT_NAME }}" \
            --branch "pr-${{ github.event.pull_request.number }}" \
            --commit-hash "${{ github.sha }}" \
            --env preview \
            2>&1 | tee deploy.log
          URL=$(grep -oP 'https://[^\s]+\.pages\.dev' deploy.log | tail -1)
          echo "preview_url=$URL" >> "$GITHUB_OUTPUT"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_PAGES_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ vars.CF_ACCOUNT_ID }}

      - name: Comment preview URL on PR
        uses: actions/github-script@v7
        with:
          script: |
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: `### Pages Preview Deployed\n\n🔗 ${process.env.PREVIEW_URL}\n\nCommit: \`${{ github.sha }}\``
            });
        env:
          PREVIEW_URL: ${{ steps.deploy.outputs.preview_url }}

  deploy-production:
    needs: build-and-type-check
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - uses: actions/download-artifact@v4
        with:
          name: pages-build-${{ github.sha }}
          path: public/

      - name: Run D1 migrations (production)
        run: |
          npx wrangler@3 d1 migrations apply prod-db --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_PAGES_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ vars.CF_ACCOUNT_ID }}

      - name: Deploy to Pages production
        run: |
          npx wrangler@3 pages deploy public \
            --project-name "${{ vars.PAGES_PROJECT_NAME }}" \
            --branch main \
            --commit-hash "${{ github.sha }}"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_PAGES_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ vars.CF_ACCOUNT_ID }}
```

## 4. tsconfig for Functions

```jsonc
// tsconfig.functions.json
{
  "extends": "./tsconfig.json",
  "compilerOptions": {
    "types": ["@cloudflare/workers-types/2026-06-01"],
    "lib": ["ES2022"],
    "target": "ES2022",
    "module": "ES2022",
    "moduleResolution": "bundler",
    "noEmit": true,
    "strict": true
  },
  "include": ["functions/**/*.ts"]
}
```

Install the correct types package version to match your `compatibility_date`:

```bash
npm install --save-dev @cloudflare/workers-types
```

## 5. _routes.json to Exclude Static Assets

```json
{
  "version": 1,
  "include": ["/api/*"],
  "exclude": ["/_next/*", "/static/*", "*.css", "*.js", "*.png"]
}
```

Without this, every request hits a Function even for static files, consuming Function
invocation quota. Add routes for all dynamic endpoints and exclude asset prefixes.

## Anti-patterns

- **Deploying via the Pages GitHub integration and wrangler in CI simultaneously.** They
  race; the integration deploys on push independently of your workflow. Disable the
  automatic GitHub integration in the Pages dashboard and own the deploy entirely from
  Actions.
- **Setting `--branch main` on PR deploys.** This overwrites the production alias.
  Always pass the PR branch name or a unique prefix for preview deployments.
- **Running D1 migrations inside the preview deploy job.** Preview databases may be
  shared; run migrations only in the production job gated behind an environment approval.
- **Omitting `--env preview` flag.** Without it, wrangler uses the top-level bindings
  from `wrangler.toml`, which point at production KV/D1 IDs.

## Gotchas

- `wrangler pages deploy` requires the *built output directory* (`public/`), not the
  source. Pass the directory, not a zip.
- The `--commit-hash` flag controls what appears in the Pages deployment history. Without
  it you lose traceability between GitHub commits and Pages deployments.
- Pages Functions have a 1 MB compressed size limit per deployment. If your function
  bundle exceeds this, switch to a Workers for Platforms dispatch namespace.
- `compatibility_flags` in `wrangler.toml` override dashboard flags. They do not merge;
  the file wins entirely when present.
- The Cloudflare API token for Pages deploy needs the **Cloudflare Pages: Edit** and
  **D1: Edit** (for migrations) permissions scoped to the target account.

## Verification

```bash
# Confirm wrangler resolves bindings from wrangler.toml (not dashboard)
npx wrangler pages dev public --env preview -- npm run dev

# List recent deployments and their status
npx wrangler pages deployment list --project-name my-pages-app

# Check function bundle size before deploy
npx wrangler pages functions build --outdir .wrangler/functions-build
du -sh .wrangler/functions-build/index.js
```

## Related

- `github-actions-cloudflare-deploy-workflow.md`
- `github-actions-cloudflare-d1-migration-pipeline.md`
- `github-actions-oidc-cloudflare-deploy.md`
- `github-actions-environment-protection.md`
- `github-actions-workers-preview-environments.md`

## Sources

- Cloudflare Docs – Pages Functions: https://developers.cloudflare.com/pages/functions/
- Wrangler Pages Deploy CLI reference: https://developers.cloudflare.com/workers/wrangler/commands/#pages-deploy
- `@cloudflare/workers-types` versioning: https://github.com/cloudflare/workers-types
- GitHub Actions `environment` protection rules: https://docs.github.com/en/actions/deployment/targeting-different-environments
