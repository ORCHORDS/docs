# Cloudflare Pages Preview Deployments

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Pull requests merge without stakeholder review in a real
browser. QA approves on localhost, production breaks on
asset paths, Workers route differences, or environment-
specific behaviour that only surfaces on the Cloudflare
edge.

## Context

Cloudflare Pages builds an isolated deployment for every
branch push automatically. Each preview gets a unique URL
derived from the branch name, runs the project's Pages
Functions code, and can be bound to separate KV namespaces
or D1 databases. Preview deployments eliminate the
"works on my machine" gap and provide a stable URL for
design review and QA sign-off before anything merges to
the production branch.

## Automatic Branch Previews and URL Patterns

Branch names are lowercased; non-alphanumeric characters
become hyphens; the result is truncated at 28 characters.
Resulting pattern:

    <sanitized-branch>.<project>.pages.dev

| Branch           | Preview URL                               |
|------------------|-------------------------------------------|
| feat/login-v2    | feat-login-v2.myapp.pages.dev             |
| fix/bug-123      | fix-bug-123.myapp.pages.dev               |
| release/2026-q3  | release-2026-q3.myapp.pages.dev           |
| main             | myapp.pages.dev  (production alias)       |

Every commit also gets an immutable, SHA-keyed URL:

    <7-char-sha>.<project>.pages.dev

Use the SHA URL in release notes so links do not shift
as the branch advances.

## Disabling Previews for Sensitive Branches

Preview URLs are publicly reachable by default. Exclude
branches whose environment bindings contain scoped secrets:

Dashboard → Settings → Builds & deployments →
Branch control → add glob patterns to the exclusion list:

    release/*
    hotfix/*

With Wrangler CLI:

```bash
wrangler pages project edit myapp \
  --preview-branch-excludes "release/*,hotfix/*"
```

Never place production API tokens in the "All environments"
binding. Use the per-environment binding panel so preview
Workers only receive preview-tier credentials.

## ENVIRONMENT Variable in Pages Functions

Pages Functions receive environment-specific variables
configured in `wrangler.toml`. Gate behaviour by value:

```typescript
// functions/api/[[path]].ts
export const onRequest: PagesFunction<Env> = async (ctx) => {
  const isProd = ctx.env.ENVIRONMENT === "production";
  if (!isProd) {
    return Response.json({ env: "preview", stub: true });
  }
  return realHandler(ctx);
};
```

Bind separate D1 databases per environment:

```toml
[env.preview.vars]
ENVIRONMENT = "preview"

[[env.preview.d1_databases]]
binding       = "DB"
database_name = "myapp-preview"
database_id   = "aaaa-preview-uuid"

[env.production.vars]
ENVIRONMENT = "production"

[[env.production.d1_databases]]
binding       = "DB"
database_name = "myapp-prod"
database_id   = "bbbb-prod-uuid"
```

## Using Preview Deployments for QA Before Merging

Add a required GitHub status check so PRs cannot merge
until the preview deployment succeeds and smoke tests pass:

```yaml
# .github/workflows/preview-qa.yml
name: Preview smoke test
on: [deployment_status]
jobs:
  smoke:
    if: >
      github.event.deployment_status.state == 'success' &&
      github.event.deployment.environment != 'production'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          URL="${{
            github.event.deployment_status.target_url }}"
          npx playwright test --base-url "$URL"
```

Mark `Preview smoke test` as a required check in branch
protection. The `deployment_status` event fires after
Cloudflare finishes the build, so tests always run against
real preview infrastructure, not a local dev server.

## Pages Build Hooks for External CI Triggers

A build hook is an inbound HTTPS endpoint that triggers
a Pages build outside the git-push flow:

1. Dashboard → Settings → Builds & deployments →
   Build hooks → Add → select target branch.
2. POST to the hook URL to start a build:

```bash
curl -X POST \
  "https://api.cloudflare.com/client/v4/pages/\
webhooks/deploy_hooks/<hook-id>"
```

Use cases: rebuild after a headless CMS publishes content,
after an upstream security patch lands, or after a manual
QA sign-off step in a ticketing workflow.

## Anti-patterns

- Sharing one KV namespace across all preview branches —
  concurrent previews overwrite each other's entries.
- Placing production API tokens in the global "All
  environments" binding where every preview URL reads them.
- Polling on a fixed timer to detect build completion
  instead of listening to `deployment_status` events.
- Signing off on `localhost` parity — missing Workers
  routes and binding differences only appear on the edge.

## Gotchas

- Branch name truncation at 28 characters can cause two
  branches that differ only after character 28 to silently
  share the same preview URL.
- `CF_PAGES_BRANCH` is a build-time variable injected by
  Wrangler; it is not available during `wrangler dev`.
- Updating `compatibility_date` only in the dashboard does
  not affect previews built from `wrangler.toml`.

## Verification

```bash
# Confirm the preview URL responds after a push
curl -sI "https://feat-login-v2.myapp.pages.dev/" \
  | head -1
# Expected: HTTP/2 200

# Confirm the preview binding is isolated from production
curl -s "https://feat-login-v2.myapp.pages.dev/api/env"
# Expected: {"env":"preview","db":"myapp-preview"}
```

## Related

- `deploy/cloudflare-workers-deploy-pipeline.md`
- `deploy/environment-parity-staging-production.md`
- `deploy/rollback-strategies-workers-pages.md`
- `testing/smoke-tests-post-deploy.md`

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/pages/configuration/preview-deployments/
- https://developers.cloudflare.com/pages/configuration/build-hooks/
- https://developers.cloudflare.com/pages/functions/bindings/
- https://developers.cloudflare.com/workers/wrangler/environments/
