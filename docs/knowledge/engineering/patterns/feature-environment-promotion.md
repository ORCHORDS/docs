# feature-environment-promotion

**Issue:** Promote features through dev → staging → production safely
**Date:** 2026-08-09
**Status:** documented

## Symptom
You develop a feature on a branch. You merge to main. It's
live. Users see the half-built feature. The deploy was supposed
to be "just the new auth, not the new dashboard."

## Root cause
**Code in main = code in production.** A single branch with no
gating means every merge is a production deploy. The risk is
too high.

## Fix
A 4-environment promotion flow:

### Environment 1: Local dev
- **Branch:** any feature branch
- **Trigger:** automatic (file save)
- **Scope:** developer's machine
- **Tools:** Next.js dev server, wrangler pages dev

### Environment 2: Preview / PR
- **Branch:** any feature branch + opened PR
- **Trigger:** push to branch (CF Pages auto-creates)
- **Scope:** public preview URL, separate DB
- **Tools:** CF Pages preview deployment

### Environment 3: Staging
- **Branch:** `main` (or `develop`)
- **Trigger:** merge to main
- **Scope:** internal team, mirrors production
- **Tools:** CF Pages environment `staging`, staging DB

### Environment 4: Production
- **Branch:** `main` (after staging verified)
- **Trigger:** manual promotion OR automated after staging tests
- **Scope:** real users
- **Tools:** CF Pages environment `production`, prod DB

## Promotion gates

Each environment has gates (automated checks):

### Local → Preview
- ✅ Typecheck
- ✅ Lint
- ✅ Unit tests
- ✅ Build

### Preview → Staging
- ✅ Integration tests
- ✅ E2E tests on the preview URL
- ✅ Visual QA (if applicable)
- ✅ Manual smoke test (if the feature is high-stakes)

### Staging → Production
- ✅ Load test (if the feature is high-traffic)
- ✅ Pen test (if the feature is security-sensitive)
- ✅ Compliance review (if the feature is regulated)
- ✅ Manual approval (the user signs off)

## The promotion mechanics

For CF Pages:
```toml
# wrangler.toml
name = "example project-pages"

# Production environment
[env.production]
name = "example project-pages"
vars = { ENVIRONMENT = "production" }

# Staging environment
[env.staging]
name = "example project-pages-staging"
vars = { ENVIRONMENT = "staging" }
```

Deploy commands:
```bash
# Deploy to staging (on merge to main)
wrangler pages deploy ./out --project-name example project --branch=main --env=staging

# Deploy to production (after staging tests pass)
wrangler pages deploy ./out --project-name example project --branch=main
```

For separate D1 per environment:
```toml
[[env.production.d1_databases]]
binding = "DB"
database_name = "example project-prod"
database_id = "abc"

[[env.staging.d1_databases]]
binding = "DB"
database_name = "example project-staging"
database_id = "def"
```

## Feature flags for promotion

For a feature that's risky, use a flag:
- **Day 1:** flag off in production, on in staging for QA
- **Day 7:** flag on for 1% in production
- **Day 14:** flag on for 10% in production
- **Day 21:** flag on for 50% in production
- **Day 28:** flag on for 100% in production

See `feature-flags.md` for the full pattern.

## Verification
- **Test:** Each environment has a known-good health endpoint
- **Live:** `curl https://<env>.example.com/api/health` returns 200
- **Audit:** Quarterly review of environment config

## Gotchas
- **Staging should mirror production as closely as possible.**
  Different DB engines, different versions, different configs
  = staging is a lie.
- **Don't share D1 between staging and production.** A
  migration applied to staging should not affect production.
- **Preview URLs are public by default.** Don't expose
  sensitive data. See `preview-environments.md`.
- **Environment-specific env vars** must be set per
  environment, not globally. Use `wrangler secret put --env staging`.
- **Promotion is a separate step from merge.** A merge to main
  shouldn't auto-deploy to production. Use a separate
  promotion workflow.

## Related
- `preview-environments.md`
- `feature-flags.md`
- `zero-downtime-deploys.md`
- `env-binding-precedence.md`
- CF Pages environments: https://developers.cloudflare.com/pages/configuration/environments/
