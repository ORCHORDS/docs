# workers-versions-gradual-rollout

Using Cloudflare Workers Versions for safe, gradual deployments with traffic
splitting between old and new code versions. This replaces the old "deploy and
pray" model where `wrangler deploy` instantly replaced 100% of production
traffic. With Versions, you can shift 1% → 10% → 50% → 100% and roll back in
seconds if error rates spike.

## Symptom

You deployed a new Worker version and it broke production for all users
instantly. There was no way to test on real traffic before going 100% live —
either you ran staging (which never matches real traffic patterns) or you
shipped to everyone at once and watched the error rate climb.

```text
14:00:00  wrangler deploy → version abc123 is now 100% of traffic
14:00:03  Error rate jumps from 0.1% to 12%  (a bug in a query path)
14:00:15  Users see 500s on checkout page
14:01:00  You frantically git revert && wrangler deploy
14:02:00  Fix is live — but 2 minutes of 12% error rate already hit users
```

The problem isn't that you shipped a bug (that's inevitable). The problem is
that the blast radius was 100% of traffic the instant you deployed.

## Background: How Versions work

Each `wrangler deploy` creates a new **immutable version** of your Worker. A
**deployment** references one or more versions and controls the percentage of
traffic each receives.

```text
┌─────────────────────────────────────────┐
│              Deployment                  │
│  ┌─────────────┐    ┌─────────────┐     │
│  │ Version A   │    │ Version B   │     │
│  │ (old, 90%)  │    │ (new, 10%)  │     │
│  │ abc123      │    │ def456      │     │
│  └─────────────┘    └─────────────┘     │
└─────────────────────────────────────────┘
         ↓                      ↓
    90% of requests        10% of requests
    go to old code         go to new code
```

Versions are immutable — you never modify a deployed version. You only shift
traffic percentages or create new versions. This makes rollback trivial: just
shift traffic back to the previous version.

## Solution: Gradual rollout workflow

### Step 1: Deploy the new version (it starts at 0% by default in dashboard)

```bash
# Deploy creates a new version but does NOT make it 100% by default
# if you use --keep-vars and gradual deploy flags
npx wrangler deploy
```

### Step 2: Shift traffic gradually via Wrangler or dashboard

```bash
# Shift 10% of traffic to the new version
npx wrangler versions deploy --version def456 --percentage 10

# Check error rates for 5-10 minutes before proceeding
# Then shift to 50%
npx wrangler versions deploy --version def456 --percentage 50

# If metrics look good, go to 100%
npx wrangler versions deploy --version def456 --percentage 100
```

### Step 3: Automated canary with health checking

```typescript
// scripts/canary-deploy.ts
// Automate: deploy 5% → check error rate → ramp up or rollback

async function canaryDeploy(versionId: string) {
  const steps = [5, 25, 50, 100];
  for (const pct of steps) {
    await shiftTraffic(versionId, pct);
    console.log(`Shifted to ${pct}%, waiting 5 min for metrics...`);
    await sleep(5 * 60 * 1000);

    const errorRate = await getErrorRate(versionId);
    const latencyP99 = await getLatencyP99(versionId);

    if (errorRate > 1.0 || latencyP99 > 2000) {
      console.error(`UNHEALTHY at ${pct}%! Rolling back.`);
      await rollback();
      return;
    }
    console.log(`Healthy at ${pct}%. Proceeding.`);
  }
  console.log(`Deploy complete: ${versionId} is 100%.`);
}
```

### Step 4: Rollback if needed

```bash
# Instant rollback to previous version — no redeploy needed
npx wrangler versions rollback
# Or target a specific version
npx wrangler versions deploy --version abc123 --percentage 100
```

Rollback is nearly instant (under 10 seconds) because the old version is still
deployed and running — you're just shifting the traffic percentage back.

## Wrangler.toml config for gradual deploys

```toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"

# By default, `wrangler deploy` goes to 100%.
# To deploy at a lower percentage by default, use:
# [deployment]
# strategy = "percentage"
# default_percentage = 0  # deploy but don't route traffic until you shift it
```

## Gotchas

- **`wrangler deploy` defaults to 100% traffic.** The plain deploy command
  still immediately routes all traffic to the new version. You must use
  `wrangler versions deploy` with `--percentage` for gradual rollouts.
- **Gradual deployments require the Workers Paid plan.** Free plan does not
  support traffic splitting between versions.
- **Versions are NOT for code branching.** Each version is a snapshot of your
  compiled Worker. You can't diff versions in source — use git for that.
  Versions are purely an operational rollout mechanism.
- **Environment variables and secrets are per-version.** If you add a new
  secret binding, you must redeploy to pick it up. Existing versions keep their
  original bindings even after you change the config.
- **Cron triggers route to the latest version only.** Scheduled events always
  hit the newest deployed version, regardless of traffic split percentages.
  If your new version has a cron handler bug, it fires even at 1% rollout.
- **Rollback doesn't undo schema changes.** If your new version ran a D1
  migration, rolling back the code doesn't roll back the database schema.
  Always design migrations to be backward-compatible with the previous version.
- **Gradual deploy percentages are approximate.** Cloudflare distributes
  traffic probabilistically across requests. At 1%, you might see 0.5%-1.5%
  of actual requests depending on colo-level rounding. Don't use tiny
  percentages for critical safety checks — 5% is a safer floor.
- **Version history is limited.** Cloudflare retains a finite number of past
  versions (check current docs for the exact limit). Very old versions are
  garbage-collected and can't be rolled back to. Tag your git commits so you
  can redeploy old code if a version ages out.
- **Service bindings and versions don't mix cleanly.** If Worker A calls
  Worker B via a service binding, and B is doing a gradual deploy, A may hit
  either version of B unpredictably. For inter-Worker RPC, prefer synchronous
  version cutover over gradual rollout.

## When to use gradual deploy vs. instant deploy

### Use gradual when:
- High-traffic Worker where bugs affect many users
- Significant logic changes (new query patterns, refactored handlers)
- First deploy of a feature flag or A/B test infrastructure
- Team has monitoring in place to detect error rate spikes

### Skip gradual (instant deploy is fine) when:
- Trivial changes (typo fix, comment update)
- Low-traffic internal tools
- You have thorough automated tests covering the change
- Development/staging environments

## Sources

- [Gradual deployments — Workers Docs](https://developers.cloudflare.com/workers/versions-and-deployments/gradual-deployments/)
- [Rollbacks — Workers Docs](https://developers.cloudflare.com/workers/versions-and-deployments/rollbacks/)
- [Introducing Rollbacks for Workers Deployments — Blog](https://blog.cloudflare.com/introducing-rollbacks-for-workers-deployments/)
