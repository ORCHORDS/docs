# zero-downtime-deploys

**Issue:** How to deploy without dropping requests
**Date:** 2026-08-09
**Status:** documented

## Symptom
You push a deploy. The 5xx error rate spikes for 30 seconds. Some
users see a 502. Mobile clients retry; you get a brief request
storm. The deploy is "successful" but the user experience is
bad.

## Root cause
A naive deploy kills the old workers before the new ones are
ready. Or: the new workers are deployed but cold-start latency
causes a brief outage. Or: a schema change requires D1
migration that fails partway.

**Source:** General principle of zero-downtime deploys:
https://en.wikipedia.org/wiki/Zero-downtime_deployment

## Fix
For CF Pages / Workers:

### Pages: atomic deploys
CF Pages is atomic. The new version is uploaded in full, then
traffic is switched. The old version continues serving until
the switch. No dropped requests.

**Source:** CF Pages deploy model:
https://developers.cloudflare.com/pages/configuration/deployments/

> "When you deploy a new commit, Pages first deploys the new
> version to all Cloudflare data centers. Once the new version
> is fully deployed, traffic is atomically switched from the old
> version to the new one."

The atomicity is the platform's job, not yours. You don't need
to do anything special.

### Workers: gradual rollout
CF Workers supports gradual rollouts via the deployment API:
```bash
# Deploy with 10% traffic to new version
wrangler deploy --version 10
# Or use the dashboard
```

The Workers platform runs the new version for 10% of requests
while the old version serves 90%. If metrics are green,
increase to 100%. If red, roll back.

### Avoid the 5 common failure modes

1. **Missing env var**
   - Symptom: 500 errors on first request
   - Fix: Run `wrangler secret list` before deploy; verify all
     required secrets exist in the target environment

2. **D1 schema mismatch**
   - Symptom: 500 errors on first DB query
   - Fix: Run migrations BEFORE deploying code that uses the new
     schema. Two-stage deploy: (a) migration, (b) code.

3. **Bundle size exceeded**
   - Symptom: deploy fails
   - Fix: Profile bundle size; split large dependencies

4. **Import path error**
   - Symptom: 500 errors on first request
   - Fix: Run the build locally and verify the output

5. **Cold start spike**
   - Symptom: p99 latency > 5s for first 10 requests
   - Fix: Add a warmup cron that pings the Worker every 30s

### Pattern: pre-deploy health check
```bash
# In CI:
# 1. Deploy to a preview environment
wrangler pages deploy ./out --project-name example project-preview --branch=preview/$PR_NUMBER

# 2. Wait for the preview URL to be reachable
sleep 10

# 3. Hit a known-good endpoint
curl -f https://$PR_NUMBER.example project-preview.pages.dev/api/health
# If non-2xx, abort the deploy

# 4. Deploy to production
wrangler pages deploy ./out --project-name example project
```

## Verification
- **Test:** Local deploy + curl test of the health endpoint
- **Live:** Monitor 5xx rate for 5 minutes after deploy
- **Audit:** Quarterly review of post-deploy error rates

## Gotchas
- **Pages Functions env vars are read at isolate init time.** A
  new secret requires a new deploy to take effect.
- **D1 migrations are NOT part of the deploy.** You must run
  them separately. Use `wrangler d1 execute` with a SQL file.
- **The `wrangler.toml` `compatibility_date` pins the runtime
  behavior.** Bumping it can change runtime semantics. Test in
  preview first.
- **CF Pages auto-rolls-back on 5xx spikes** in some cases. Check
  the dashboard for the auto-rollback status.
- **The `pages_build_output_dir` must exist before deploy.**
  `next build` must run first.

## Related
- `wrangler-deploys.md`
- `preview-environments.md`
- CF Pages: https://developers.cloudflare.com/pages/configuration/deployments/
- CF Workers: https://developers.cloudflare.com/workers/configuration/versions-and-rollbacks/
