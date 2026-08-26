# wrangler-deploy-github-actions-workers

**Issue:** Wrangler deploy in GitHub Actions for Cloudflare Workers
**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

CI pipeline deploys a Cloudflare Worker with `wrangler deploy` but the
step fails with `authentication error: 10000` or silently publishes to
the wrong environment because the `CLOUDFLARE_API_TOKEN` secret was
not scoped correctly, or because `--env` was omitted and the default
`wrangler.toml` environment was used instead of `production`.

## Context

Wrangler reads credentials from the environment variable
`CLOUDFLARE_API_TOKEN` (preferred) or `CLOUDFLARE_ACCOUNT_ID` +
`CLOUDFLARE_API_KEY`. GitHub Actions stores these as encrypted
repository or organisation secrets. Environment-specific behaviour
(routes, KV namespaces, D1 bindings, compatibility dates) must live
in named `[env.<name>]` stanzas in `wrangler.toml`; a flat config
deploys only to the default route, which is almost never `production`.

**Source:** Cloudflare Docs — Wrangler CI/CD; GitHub Actions —
Encrypted secrets.

## The "minimal wrangler.toml per environment" pattern

```toml
# wrangler.toml
name       = "my-worker"
main       = "src/index.ts"
compatibility_date = "2026-08-01"

[env.staging]
routes = [{ pattern = "staging.example.com/*", zone_name = "example.com" }]

[[env.staging.kv_namespaces]]
binding  = "CACHE"
id       = "abc123stagingkvid"

[env.production]
routes = [{ pattern = "api.example.com/*", zone_name = "example.com" }]

[[env.production.kv_namespaces]]
binding  = "CACHE"
id       = "def456productionkvid"
```

Always use named environments. Omitting `--env` in CI picks up the
root stanza and deploys to whatever route is defined there (often none
or an old dev route).

## The "GitHub Actions CLOUDFLARE_API_TOKEN" pattern

Create the token in the Cloudflare dashboard:
**My Profile → API Tokens → Create Token → Edit Cloudflare Workers**.
Scope the token to the specific account and zone.

```yaml
# .github/workflows/deploy.yml
name: Deploy Workers

on:
  push:
    branches: [main]

jobs:
  deploy-staging:
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm

      - run: npm ci

      - name: Deploy to staging
        run: npx wrangler deploy --env staging
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

  deploy-production:
    runs-on: ubuntu-latest
    environment: production
    needs: deploy-staging
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm

      - run: npm ci

      - name: Deploy to production
        run: npx wrangler deploy --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
```

Use GitHub's `environment:` key so secret access requires a manual
approval gate before `deploy-production` runs.

## The "parallel Worker + Pages deploy" pattern

Deploy a Worker API and its Pages front end in parallel, then gate
health checks on both:

```yaml
  deploy-worker-and-pages:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - run: npm ci

      - name: Deploy Worker (background)
        run: npx wrangler deploy --env production &
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

      - name: Deploy Pages (background)
        run: |
          npx wrangler pages deploy ./dist \
            --project-name my-pages-project \
            --branch main &
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

      - name: Wait for both deploys
        run: wait
```

Both deploys start immediately; `wait` blocks until both finish.
Total wall-clock time is the slower of the two, not their sum.

## The "deployment verification with curl" pattern

After deploy, probe the Worker's health endpoint and assert the
deployed git SHA matches the expected commit:

```yaml
      - name: Verify Worker health
        run: |
          STATUS=$(curl -sf -o /dev/null -w "%{http_code}" \
            https://api.example.com/health)
          [ "$STATUS" = "200" ] || \
            (echo "health check failed: $STATUS" && exit 1)

      - name: Verify deployed version
        run: |
          SHA=$(curl -sf https://api.example.com/version | \
            jq -r '.sha')
          [ "$SHA" = "$GITHUB_SHA" ] || \
            (echo "version mismatch: $SHA != $GITHUB_SHA" && exit 1)
```

Implement `GET /health` and `GET /version` in the Worker:

```typescript
// src/index.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    if (url.pathname === "/health")
      return new Response("ok", { status: 200 });
    if (url.pathname === "/version")
      return Response.json({ sha: "__COMMIT_SHA__" });
    // …
  },
};
```

Replace `__COMMIT_SHA__` at build time:

```yaml
      - run: |
          sed -i "s/__COMMIT_SHA__/$GITHUB_SHA/g" src/index.ts
```

## Environment vs. secret matrix

```
+-------------------+----------------+-----------------------------+
| GitHub secret     | Scope          | Used for                    |
+-------------------+----------------+-----------------------------+
| CLOUDFLARE_       | Org or repo    | wrangler auth (all envs)    |
| API_TOKEN         |                |                             |
+-------------------+----------------+-----------------------------+
| CLOUDFLARE_       | Org or repo    | wrangler account resolution |
| ACCOUNT_ID        |                |                             |
+-------------------+----------------+-----------------------------+
| CLOUDFLARE_       | Repo env:      | Per-env DB URL, KV id,      |
| *_STAGING /       | staging /      | secret values injected via  |
| *_PRODUCTION      | production     | `wrangler secret put`       |
+-------------------+----------------+-----------------------------+
```

## Anti-patterns

- **Storing `CLOUDFLARE_API_TOKEN` in `wrangler.toml`.** It is
  committed to the repo. Use GitHub secrets only.
- **Running `wrangler deploy` without `--env`.** Publishes to the
  default (often dev) route, silently skipping production.
- **Using `CLOUDFLARE_GLOBAL_API_KEY` in CI.** This is the
  account-owner key with full access. Use a scoped API token.
- **Skipping the health-check step.** A successful `wrangler deploy`
  only means the upload succeeded, not that the Worker starts.
- **No `needs:` between staging and production jobs.** Both deploy
  in parallel; a broken staging build reaches production.

## Gotchas

- `wrangler deploy` exits 0 if the Worker compiles and uploads even
  if the Worker's `fetch` handler throws at runtime. Always run a
  health-check curl after deploy.
- The Cloudflare API token must have the **Workers Scripts: Edit**
  permission and, if routes are used, **Zone: Edit** as well.
- `npx wrangler` resolves the local `node_modules/.bin/wrangler`
  version, which keeps CI and local behaviour in sync. Avoid
  `npm install -g wrangler` in CI.
- Pages deployments with `wrangler pages deploy` do not respect
  `wrangler.toml` env stanzas; they use `--project-name` and
  `--branch` instead.

## Verification

- **CI:** After `deploy-production`, the curl health check returns
  HTTP 200 and the version endpoint returns the expected commit SHA.
- **Live:** `curl -I https://api.example.com/health` returns
  `HTTP/2 200` with `cf-ray` header present.
- **Audit:** Cloudflare dashboard → Workers → Deployments shows the
  new deployment timestamped within 60 s of the CI run.

## Related

- `documentation/docs/policies/deploy/canary-workers-gradual-traffic-split.md`
- `documentation/docs/policies/deploy/workers-secrets-rotation-zero-downtime.md`
- `documentation/docs/policies/deploy/cloudflare-pages-build-cache-optimization.md`
- `documentation/docs/policies/deploy/oidc-federated-deploy-credentials.md`
- `documentation/docs/policies/deploy/deployment-verification-smoke-tests.md`

## Sources

- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://developers.cloudflare.com/workers/ci-cd/github-actions/
- https://docs.github.com/en/actions/security-for-github-actions/\
  security-guides/using-secrets-in-github-actions
