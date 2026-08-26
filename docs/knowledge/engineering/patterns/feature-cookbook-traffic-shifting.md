# feature-cookbook-traffic-shifting

**Issue:** Traffic shifting — canary, percentage, geo
**Date:** 2026-08-09
**Status:** documented

## Symptom
You deploy a new version. 100% of users get it. The new
version has a bug. You roll back. Half the users had a
bad experience. You wish you'd tested with 1% first.

## Root cause
**Big-bang deploys are risky.** Use traffic shifting.

**Source:** AWS — Traffic shifting.

## The "canary" pattern

For canary, 1% of traffic to the new version:
```
v1 (stable):  99%
v2 (canary):  1%
```

The canary catches the issue with minimal impact.

## The "percentage" pattern

For percentage, gradually increase:
```
Hour 0:  1% v2, 99% v1
Hour 1:  10% v2, 90% v1
Hour 2:  50% v2, 50% v1
Hour 3: 100% v2, 0% v1
```

The percentage grows; the team can stop at any time.

## The "CF Workers traffic" pattern

For CF, use the version + percentage:
```bash
# Deploy v2 with 0% traffic
wrangler versions deploy --version-id v2 --percentage 0

# Gradually increase
wrangler versions deploy --version-id v2 --percentage 10
wrangler versions deploy --version-id v2 --percentage 50
wrangler versions deploy --version-id v2 --percentage 100
```

CF handles the routing.

## The "CF load balancer" pattern

For LB-based:
```ts
const origins = [
  { name: 'v1', address: 'v1.example.com', weight: 1.0 },
  { name: 'v2', address: 'v2.example.com', weight: 0.0 },
];

// Shift
origins.find(o => o.name === 'v2')!.weight = 0.05;  // 5% canary
```

The LB handles the routing.

## The "session affinity" pattern

For sticky canary, a cookie determines the version:
```ts
const cookie = request.headers.get('cookie') ?? '';
const canaryMatch = cookie.match(/canary=([^;]+)/);

if (canaryMatch && canaryMatch[1] === 'v2') {
  return fetch('https://v2.example.com' + url.pathname);
} else if (Math.random() < 0.05) {
  return fetch('https://v2.example.com' + url.pathname, {
    headers: { 'set-cookie': 'canary=v2; path=/; max-age=86400' },
  });
} else {
  return fetch('https://v1.example.com' + url.pathname);
}
```

The same user always gets the same version.

## The "geo-canary" pattern

For geo, start with one region:
```ts
const country = request.cf?.country ?? 'US';
if (country === 'CA') {
  return fetch('https://v2.example.com' + url.pathname);  // Canada gets v2
} else {
  return fetch('https://v1.example.com' + url.pathname);
}
```

The canary starts in a low-risk region.

## The "tenant canary" pattern

For B2B, canary one tenant:
```ts
const tenantId = request.headers.get('x-tenant-id');
if (tenantId === 'tenant-canary') {
  return fetch('https://v2.example.com' + url.pathname);
} else {
  return fetch('https://v1.example.com' + url.pathname);
}
```

A trusted tenant tests the new version.

## The "automated rollout" pattern

For automated rollout, monitor metrics:
```ts
async function autoRollout(env: Env): Promise<void> {
  const metrics = await getMetrics(env);
  const errorRateV2 = metrics.v2.errorRate;
  const errorRateV1 = metrics.v1.errorRate;

  if (errorRateV2 > errorRateV1 * 1.5) {
    // Rollback
    logEvent('rollout.rollback', 'warn', { reason: 'error_rate_spike' });
    await setRolloutPercentage('v2', 0);
  } else if (errorRateV2 < errorRateV1 * 1.1) {
    // Roll forward
    const currentPct = await getRolloutPercentage('v2');
    await setRolloutPercentage('v2', Math.min(currentPct + 10, 100));
  }
}
```

The rollout is automated.

## The "canary metrics" pattern

For canary metrics, compare:
- **Error rate:** v1 vs v2
- **Latency:** v1 vs v2
- **Conversion:** v1 vs v2
- **User feedback:** v1 vs v2

```ts
async function compareVersions(env: Env): Promise<void> {
  const v1 = await getMetrics('v1', env);
  const v2 = await getMetrics('v2', env);

  console.log({
    msg: 'canary.metrics',
    errorRate: { v1: v1.errorRate, v2: v2.errorRate },
    latencyP99: { v1: v1.latencyP99, v2: v2.latencyP99 },
  });
}
```

The metrics drive the rollout.

## The "instant rollback" pattern

For instant rollback, set the percentage:
```bash
# Rollback to 100% v1
wrangler versions deploy --version-id v1 --percentage 100
```

Rollback is instant.

## The "traffic shifting anti-pattern" anti-patterns

### 1. Big-bang deploy
- **Issue:** All users are affected by a bad version
- **Fix:** Canary + percentage

### 2. No rollback plan
- **Issue:** Stuck with a bad version
- **Fix:** Always have v1 available

### 3. No metrics
- **Issue:** Don't know if v2 is OK
- **Fix:** Compare metrics

### 4. No canary
- **Issue:** First sign of issue is user complaints
- **Fix:** 1% canary first

### 5. Long canary
- **Issue:** A 1% canary for 1 week delays the rollout
- **Fix:** Automate the rollout

## Verification
- **Test:** Canary works
- **Test:** Rollout is gradual
- **Test:** Rollback is instant
- **Live:** Metrics are compared
- **Audit:** Annual review of rollout process

## Gotchas
- **The "big-bang deploy" anti-pattern.** Canary first.
- **The "no rollback plan" anti-pattern.** Always have
  v1.
- **The "no metrics" anti-pattern.** Compare versions.

## Related
- `feature-cookbook-blue-green.md`
- `feature-cookbook-load-balancing.md`
- `feature-flags.md`
- `safe-deploy-checklist.md`
- `zero-downtime-deploys.md`
- `feature-observability-pattern.md`
- CF versions: https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
