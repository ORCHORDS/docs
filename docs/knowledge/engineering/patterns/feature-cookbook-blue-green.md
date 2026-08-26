# feature-cookbook-blue-green

**Issue:** Blue-green deployment — zero-downtime, instant rollback
**Date:** 2026-08-09
**Status:** documented

## Symptom
You deploy. The deploy takes 5 min. During the deploy,
the app is down. You deploy at 2am to minimize impact.
You get paged. You wish there were no downtime.

## Root cause
**In-place deploys have downtime.** Use blue-green.

**Source:** AWS — Blue/Green deploys.

## The "blue-green" concept

Two identical environments: blue (current) and green
(new). Traffic is switched from blue to green instantly.

```
Before deploy: 100% blue
After deploy:  0% blue, 100% green
Rollback:      100% blue, 0% green
```

No downtime, instant rollback.

## The "CF Workers blue-green" pattern

For CF Workers, use a version + 100% traffic shift:
```ts
// Deploy with 0% traffic
wrangler versions deploy --version-id v2 --percentage 0

// Test
curl https://v2.example.com/health

// Shift 100% to v2
wrangler versions deploy --version-id v2 --percentage 100

// Rollback
wrangler versions deploy --version-id v1 --percentage 100
```

CF handles the routing.

## The "DNS blue-green" pattern

For DNS, switch the A/CNAME record:
```
blue.example.com → 1.2.3.4
green.example.com → 5.6.7.8

// Deploy: change the record
// www.example.com → 5.6.7.8 (green)
```

DNS TTL should be low (60s) for quick switch.

## The "LB blue-green" pattern

For LB, two origin pools:
```ts
const origins = [
  { name: 'blue', address: '1.2.3.4', weight: 1 },
  { name: 'green', address: '5.6.7.8', weight: 0 },  // New version, no traffic yet
];

// Shift traffic
origins.find(o => o.name === 'green')!.weight = 1;
origins.find(o => o.name === 'blue')!.weight = 0;
```

The LB handles the shift.

## The "DB blue-green" pattern

For DB, dual-write + cutover:
```ts
// Phase 1: dual-write to old + new
async function writeOrder(order: Order) {
  await env.DB_OLD!.prepare(`INSERT INTO orders ...`).run();
  await env.DB_NEW!.prepare(`INSERT INTO orders ...`).run();
}

// Phase 2: read from new
async function readOrder(id: string) {
  return env.DB_NEW!.prepare(`SELECT * FROM orders WHERE id = ?`).bind(id).first();
}

// Phase 3: drop the old
```

The DB is migrated without downtime.

## The "schema migration blue-green" pattern

For schema migration:
1. **Expand:** Add the new column (no removal yet)
2. **Dual-write:** Write to both old + new
3. **Backfill:** Migrate old data to new
4. **Read new:** Switch reads to new
5. **Contract:** Remove the old column (in a later
   release)

This is the "expand-contract" pattern. No downtime.

## The "feature flag blue-green" pattern

For feature flags, the new feature is gated:
```ts
if (await isFeatureEnabled('new_ui', user, env)) {
  return renderNewUI();
} else {
  return renderOldUI();
}
```

The new UI is rolled out gradually.

## The "canary blue-green" pattern

For canary, 5% to new:
```ts
// 95% blue, 5% green
const weights = [
  { name: 'blue', weight: 0.95 },
  { name: 'green', weight: 0.05 },
];
```

A small percentage tests the new version.

## The "rollback" pattern

For rollback, the old version is still available:
```ts
// Rollback: shift back to blue
const weights = [
  { name: 'blue', weight: 1 },
  { name: 'green', weight: 0 },
];
```

Rollback is instant.

## The "smoke test" pattern

For a smoke test before cutover:
```ts
// 1. Deploy green
// 2. Hit green directly (bypass LB)
const response = await fetch('https://green.internal/health');
if (!response.ok) throw new Error('Green is unhealthy');

// 3. Hit green with a test query
const test = await fetch('https://green.internal/api/test');
if (!test.ok) throw new Error('Test failed');

// 4. Shift traffic
```

The smoke test catches the issue before users do.

## The "blue-green anti-pattern" anti-patterns

### 1. No smoke test
- **Issue:** The new version is broken
- **Fix:** Smoke test before cutover

### 2. No rollback plan
- **Issue:** The new version is broken; how do you
  recover?
- **Fix:** Always have the old version available

### 3. Schema change without expand-contract
- **Issue:** The DB is down during the migration
- **Fix:** Expand-contract pattern

### 4. No health check
- **Issue:** The new version is unhealthy
- **Fix:** Health check before cutover

### 5. High DNS TTL
- **Issue:** DNS takes 1h to propagate; rollback is slow
- **Fix:** TTL < 60s

## Verification
- **Test:** Blue-green deploys work
- **Test:** Rollback works
- **Test:** Smoke test catches issues
- **Live:** Health is monitored
- **Audit:** Annual review of deploy process

## Gotchas
- **The "no smoke test" anti-pattern.** Test the new
  version before traffic.
- **The "no rollback plan" anti-pattern.** Always have
  the old version.
- **The "schema change without expand-contract"
  anti-pattern.** Use expand-contract for migrations.

## Related
- `zero-downtime-deploys.md`
- `safe-deploy-checklist.md`
- `zero-downtime-db-migration.md`
- `feature-flags.md`
- `feature-observability-pattern.md`
- `feature-cookbook-load-balancing.md`
- `feature-cookbook-disaster-recovery.md`
- AWS blue-green: https://docs.aws.amazon.com/whitepapers/latest/blue-green-deployments/
