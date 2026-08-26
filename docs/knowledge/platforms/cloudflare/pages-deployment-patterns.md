# Cloudflare Pages Deployment Patterns

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your frontend deployment process is fragile — manual builds pushed to a
static hosting provider, no preview environments for pull requests, and
rollbacks require rebuilding and redeploying from scratch. Environment
variables are managed ad hoc, and there is no consistent way for
reviewers to see changes before they merge.

## Context

Cloudflare Pages provides a Git-connected deployment platform for static
sites and full-stack applications (via Pages Functions). Every push gets
a build, every PR gets a unique preview URL, and production deployments
happen on merge to the main branch. Pages deploys to Cloudflare's global
edge network (300+ cities) with automatic SSL, HTTP/3, and asset
optimization. In 2026, Pages supports server-side rendering frameworks
(Next.js, Nuxt, SvelteKit, Astro) through Pages Functions, blurring the
line between static hosting and full-stack deployment.

## Deployment triggers

### Git integration

```
main branch   → Production deployment (your-project.pages.dev)
PR branch     → Preview deployment (abc123.your-project.pages.dev)
Feature branch → Preview deployment (branch-name.your-project.pages.dev)
```

Every commit to any branch creates a deployment. Preview URLs are unique
per commit and permanent — they do not change after the PR is merged or
the branch is deleted.

### Direct upload

For CI/CD pipelines that build outside Cloudflare:

```bash
# Upload a pre-built directory
npx wrangler pages deploy ./dist --project-name=my-project

# Upload with a specific branch name (creates preview)
npx wrangler pages deploy ./dist --project-name=my-project --branch=feature-x
```

## Build configuration

### Framework presets

Pages auto-detects common frameworks and configures build settings:

| Framework | Build command | Output directory |
|---|---|---|
| Next.js | `npx @cloudflare/next-on-pages` | `.vercel/output/static` |
| Nuxt | `nuxt build` | `.output/public` |
| Astro | `astro build` | `dist` |
| SvelteKit | `vite build` | `.svelte-kit/cloudflare` |
| Vite/React | `vite build` | `dist` |
| Hugo | `hugo` | `public` |

### Custom build configuration

```toml
# wrangler.toml (Pages project)
name = "my-project"
pages_build_output_dir = "./dist"

[vars]
API_URL = "https://api.example.com"

[[kv_namespaces]]
binding = "CACHE"
id = "abc123"
```

## Monorepo support

### Build watch paths

Configure Pages to only rebuild when files in specific directories
change:

```
Root directory: apps/web
Include paths:
  - apps/web/**
  - packages/shared/**
  - packages/ui/**
Exclude paths:
  - apps/api/**
  - apps/mobile/**
```

This prevents unnecessary rebuilds when changes are made to unrelated
packages in the monorepo.

### Turborepo integration

```json
{
  "scripts": {
    "build": "turbo run build --filter=web..."
  }
}
```

The `--filter=web...` flag builds only the `web` package and its
dependencies, skipping unrelated packages. Combined with Pages' build
watch paths, this minimizes build time and resource usage.

## Pages Functions (server-side)

Pages Functions run on Cloudflare Workers, providing server-side logic
at the edge:

```
functions/
├── api/
│   ├── users.ts        → /api/users
│   └── orders/
│       └── [id].ts     → /api/orders/:id
└── _middleware.ts       → Runs on all requests
```

```typescript
// functions/api/users.ts
export const onRequestGet: PagesFunction<Env> = async (context) => {
  const users = await context.env.DB.prepare(
    'SELECT * FROM users LIMIT 10'
  ).all();
  return Response.json(users.results);
};
```

## Environment variables and secrets

```
Production variables:  Set in Pages dashboard or wrangler.toml [vars]
Preview variables:     Set separately for preview deployments
Secrets:               Set via dashboard or `wrangler pages secret put`
```

Preview deployments can use different environment variables than
production — for example, pointing to a staging API instead of
production.

## Rollback

Pages keeps every deployment permanently. Rolling back is instant —
select a previous deployment in the dashboard or use the API:

```bash
# List deployments
npx wrangler pages deployment list --project-name=my-project

# Rollback to a specific deployment
npx wrangler pages deployment create --project-name=my-project \
  --deployment-id=<previous-deployment-id>
```

Rollbacks take effect globally in seconds because they switch the
routing pointer, not rebuild or redeploy assets.

## Anti-patterns

- **No preview deployments** — merging frontend changes without visual
  review. Preview URLs let reviewers see the actual rendered output, not
  just code diffs.
- **Hardcoded environment URLs** — using `https://api.production.com`
  directly in frontend code instead of environment variables. Preview
  deployments will hit production APIs.
- **Ignoring build watch paths in monorepos** — every push to the
  monorepo triggers a rebuild of every Pages project. Configure watch
  paths to build only when relevant files change.
- **Large asset bundles** — uploading unoptimized images and videos
  through Pages. Use Cloudflare Images or R2 for large assets and
  reference them by URL.

## Gotchas

- **Function size limits** — each Pages Function is limited to 1 MB
  compressed (Workers free) or 10 MB (Workers paid). Large server-side
  bundles must be split or dependencies externalized.
- **Node.js compatibility** — Pages Functions run on the Workers runtime,
  not Node.js. Some Node.js APIs are unavailable. Use the
  `nodejs_compat` compatibility flag for partial Node.js API support.
- **Build minutes** — free plan includes 500 build minutes/month. Large
  Next.js builds can consume 3-5 minutes each. Use direct upload from
  external CI to avoid consuming build minutes.
- **Custom domains** — custom domains require DNS to be on Cloudflare
  (full or CNAME setup). External DNS with a CNAME to pages.dev works
  but loses some Cloudflare features.

## Verification

- Every PR gets a preview deployment with a unique URL.
- Production deploys only from the main branch.
- Rollback to previous deployment takes less than 60 seconds.
- Monorepo build watch paths are configured to avoid unnecessary builds.
- Environment variables are separate for production and preview.
- Pages Functions handle server-side logic without a separate backend
  deployment.

## Related

- `documentation/docs/policies/cloudflare/workers-development-patterns.md`
- `documentation/docs/policies/cloudflare/r2-object-storage.md`
- `documentation/docs/policies/infra/ci-cd-pipeline-design.md`

## Source URLs (verified 2026-08-16)

- Cloudflare Pages documentation — https://developers.cloudflare.com/pages/
- Pages Functions — https://developers.cloudflare.com/pages/functions/
- Pages framework guides — https://developers.cloudflare.com/pages/framework-guides/
- Monorepo configuration — https://developers.cloudflare.com/pages/configuration/monorepos/
