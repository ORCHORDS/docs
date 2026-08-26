# wrangler-deploys

**Issue:** `wrangler pages deploy` gotchas — auth, env, output
**Date:** 2026-08-09
**Status:** documented

## Symptom
`wrangler pages deploy ./out --project-name example project` fails with
"Authentication error [code: 10000]". You have a CF API token
but wrangler doesn't see it.

## Root cause
`wrangler` uses the `CLOUDFLARE_API_TOKEN` environment variable
for auth. The token must have:
- Account → Cloudflare Pages: Edit
- Account → Account Settings: Read

If the token is missing, expired, or has the wrong scope, wrangler
fails.

**Source:** wrangler auth docs:
https://developers.cloudflare.com/workers/wrangler/configuration/

> "Set the CLOUDFLARE_API_TOKEN environment variable to the API
> token you generated in the Cloudflare dashboard."

## Fix
For CI/CD (no interactive login):

```bash
# Set the token
export CLOUDFLARE_API_TOKEN="<your-token>"

# Deploy
cd apps/web
wrangler pages deploy ./out \
  --project-name example project \
  --commit-dirty=true
```

For local dev (interactive):
```bash
wrangler login
# Opens a browser, you approve, wrangler stores a token locally
```

### Required token scopes
For Pages deployment, the token needs:
- **Account → Cloudflare Pages: Edit** (deploy)
- **Account → Cloudflare Pages: Read** (verify project exists)
- **Account → Account Settings: Read** (resolve account ID)

For Workers deployment (separate from Pages):
- **Account → Workers Scripts: Edit** (deploy)
- **Account → Workers KV Storage: Edit** (if using KV)
- **Account → Workers R2 Storage: Edit** (if using R2)
- **Account → Workers Scripts D1: Edit** (if using D1)
- **Account → Account Settings: Read**

### Storing the token securely
**Don't put the token in `.env`** (often committed by accident).
**Don't put it in `wrangler.toml`** (visible in git history).
Use a secret manager (1Password CLI, GitHub Actions secrets,
CF Workers Secrets).

For GH Actions:
```yaml
# .github/workflows/deploy.yml
- name: Deploy to CF Pages
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
  run: |
    cd apps/web
    pnpm exec wrangler pages deploy ./out --project-name example project --commit-dirty=true
```

## Verification
- **Test:** Local `wrangler pages dev` serves the Functions correctly
- **Live:** Deploy succeeds, the new URL returns 200, the old URL
  redirects (if applicable)
- **Audit:** The deploy is logged in CF audit log

## Gotchas
- **`--commit-dirty=true`** allows deploying with uncommitted
  changes. Useful for CI (the build artifact is the truth, not
  the working tree). Dangerous for local dev (deploys accidental
  changes).
- **`wrangler pages deploy` requires the project to already
  exist.** First-time setup: `wrangler pages project create example project`
  (one-time, interactive).
- **The deploy URL is `<project>-<hash>.pages.dev`** for preview
  deploys. Custom domains (`example.com`) attach to the main
  branch deployment.
- **CF Pages Functions env vars are per-environment.** Set them
  in the CF dashboard or via `wrangler pages secret put NAME`
  (one env var at a time, interactive).
- **For Workers (not Pages), use `wrangler deploy`** with
  `wrangler.toml` config. Different command, different auth.
- **Tokens have a 1-year max lifetime** for some scopes. Rotate
  before expiry (see `secrets-rotation-runbook.md`).

## Related
- `secrets-rotation-runbook.md`
- `next-static-export-pages.md` (the build that produces the
  output)
- `pages-static-vs-functions.md` (the routing model)
- wrangler docs: https://developers.cloudflare.com/workers/wrangler/
