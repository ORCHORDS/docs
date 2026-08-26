# preview-environments

**Issue:** PR preview environments — setup, cost, isolation
**Date:** 2026-08-09
**Status:** documented

## Symptom
You open a PR. You want to share a live preview with a designer
or stakeholder. The local dev server is unreachable. You have no
preview URL. The PR review is delayed by hours of "can you
deploy a preview?"

## Root cause
CF Pages has **preview deployments** built-in. Every push to a
non-main branch gets a unique preview URL. You just have to
configure it (or use the default).

**Source:** CF Pages preview deployments:
https://developers.cloudflare.com/pages/configuration/preview-deployments/

> "Each time you push a commit to a branch, Pages will deploy
> your site to a unique URL."

## Fix
CF Pages auto-creates preview URLs for every branch push. The
URL is `https://<commit-hash>.<project>.pages.dev`. Configure
in the dashboard → Pages → project → Settings → Builds & deployments.

### Branch preview controls
- **All branches** get previews (default)
- **None** — only main gets deployed
- **Custom branches** — specify a list (e.g. only `staging`,
  `release/*`)

### PR-specific previews
For PR previews, you need the GH integration:
1. Install the CF Pages app on GH
2. Connect the repo
3. Open a PR → CF comments with the preview URL

### Environment variables per preview
Each preview is a separate "environment" in CF Pages. You can
configure per-environment env vars:
- **Production** (`main` branch): real DB, real secrets
- **Preview** (other branches): staging DB, fake secrets

```bash
# In wrangler.toml or dashboard:
[env.preview]
name = "example project-preview"
vars = { ENV = "preview" }
```

### Cost considerations
Preview deployments:
- **Pages:** unlimited preview deploys on the free plan; ~500k
  requests/month per preview
- **Workers:** each preview is a separate isolate (cold start
  cost on first request)
- **D1:** shared across all environments (preview + prod
  read/write the same DB unless you use environment-specific
  bindings)

For D1 isolation, use separate databases per environment:
```toml
# wrangler.toml
[[d1_databases]]
binding = "DB"
database_name = "example project-prod"
database_id = "abc..."

[env.preview]
[[env.preview.d1_databases]]
binding = "DB"
database_name = "example project-preview"
database_id = "def..."
```

## Verification
- **Test:** Open a PR → comment is posted with preview URL
- **Live:** Preview URL is reachable, the PR's code is visible
- **Audit:** Old preview URLs are cleaned up after PR merge/close

## Gotchas
- **Preview URLs are public** by default. Don't expose secrets
  in the URL or in the page content. The preview is reachable
  by anyone who has the URL.
- **D1 migrations apply to ALL environments.** If you push a
  migration to a preview branch, it runs against the preview DB.
  But if the prod DB has the same migration in a separate branch,
  you can have drift. Use environment-specific DBs.
- **Custom domains don't work on previews.** Only the auto-
  generated `*.pages.dev` URL is available.
- **Preview URLs are NOT deleted when the branch is deleted.**
  You must explicitly delete them in the CF dashboard, or let
  them age out (CF does this after 90 days of inactivity).
- **The PR comment webhook requires the CF GitHub App.** Without
  it, the comment is not posted, but the preview URL is still
  created.

## Related
- `wrangler-deploys.md`
- `pages-static-vs-functions.md`
- CF Pages preview: https://developers.cloudflare.com/pages/configuration/preview-deployments/
