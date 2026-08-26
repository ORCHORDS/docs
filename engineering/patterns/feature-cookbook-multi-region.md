# feature-cookbook-multi-region

**Issue:** Multi-region deployment — replication, geo-routing, latency
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your app is in US East. A user in Asia has 500ms latency.
They complain. You add a CDN. Latency drops to 100ms.
The user is in Asia; the data is in US. You need a
multi-region setup.

## Root cause
**A single region means single-region latency.** For
global users, multi-region is the answer.

**Source:** CF multi-region docs:
https://developers.cloudflare.com/workers/learning/using-workers/

## The "CF global" pattern

CF Workers run globally by default. Each request is
handled by the closest CF POP.

```
User (Tokyo) → CF POP (Tokyo) → CF POP (US East) [if needed]
```

For Workers, the global is built-in.

## The "D1 replica" pattern

D1 has read replicas globally:
- **Writes:** Go to the primary region
- **Reads:** Served from the closest replica
- **Replication:** Eventual (a few seconds)

```ts
// Reads can be from any replica
const user = await env.DB!.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first();

// Writes must be sent to the primary
await env.DB!.prepare(`INSERT INTO users ...`).bind(...).run();
```

D1 handles the routing.

## The "R2 global" pattern

R2 is globally available; reads go to the closest edge:
```ts
// R2 is global
const object = await env.R2!.get('users/u_123.json');
```

R2 has no region; the closest edge serves the request.

## The "DO regional" pattern

DOs are regional. For multi-region, use multiple DOs:
```ts
// In different regions
const usDO = env.DO_US.idFromName('global-state');
const euDO = env.DO_EU.idFromName('global-state');
const asiaDO = env.DO_ASIA.idFromName('global-state');
```

Each region has its own DO; the client is routed by CF.

## The "geo-routing" pattern

For geo-routing, use CF's location headers:
```ts
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const country = request.cf?.country ?? 'US';
    const city = request.cf?.city ?? 'unknown';

    if (country === 'US' || country === 'CA') {
      return handleUSRequest(request, env, ctx);
    } else if (country === 'DE' || country === 'FR' || country === 'UK') {
      return handleEURequest(request, env, ctx);
    } else {
      return handleAsiaRequest(request, env, ctx);
    }
  },
};
```

The request is routed by geography.

## The "data residency" pattern

For data residency (GDPR), the user's data is in their
region:
```ts
async function getDbForUser(user: User, env: Env): Promise<D1Database> {
  if (user.region === 'EU') return env.DB_EU;
  if (user.region === 'APAC') return env.DB_APAC;
  return env.DB_US;
}
```

The data is in the user's region.

## The "active-active" pattern

For active-active, multiple regions handle traffic:
- **Reads:** Any region
- **Writes:** Routed to the primary region
- **Replication:** Async (eventual consistency)

```ts
// Read from local DB
const user = await getLocalDb(env).prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first();

// Write to primary DB
await getPrimaryDb(env).prepare(`UPDATE users SET ... WHERE id = ?`).bind(...).run();
```

The write is async-replicated.

## The "active-passive" pattern

For active-passive, one region is primary, others are
standby:
- **Reads + Writes:** Primary
- **Standby:** Replicated, ready for failover

```ts
async function getDb(env: Env): Promise<D1Database> {
  // Use the primary
  return env.DB_PRIMARY;
}
```

Simpler but no failover.

## The "failover" pattern

For failover, the standby becomes primary:
```ts
async function getDb(env: Env, isFailover = false): Promise<D1Database> {
  if (isFailover) return env.DB_SECONDARY;
  return env.DB_PRIMARY;
}
```

The failover is manual or automatic.

## The "geo-replication" pattern

For replicating across regions, use CRDTs or eventual
consistency:
- **CRDTs:** Conflict-free replicated data types
- **Eventual consistency:** Updates propagate async
- **Last-write-wins:** Simple but loses updates

For most apps, eventual consistency is enough.

## The "latency budget" pattern

For latency budgets:
- **Target:** p99 < 200ms
- **Region-to-region:** 100-200ms (US to EU)
- **Within region:** < 50ms

A multi-region setup with 500ms latency is worse than
single-region with 100ms.

## The "data consistency" pattern

For data consistency across regions:
- **Single primary:** Writes are routed to one region
- **Async replication:** The other regions receive
  updates
- **Conflict resolution:** Last-write-wins or
  application-specific

For most apps, single primary + async replication.

## The "compliance" pattern

For data residency (GDPR, China data law):
- **EU users:** Data in EU
- **US users:** Data in US
- **APAC users:** Data in APAC

The data is segregated by region.

## The "monitoring" pattern

For multi-region, monitor per region:
```ts
metrics.increment('requests_total', { region: 'us', status: '200' });
metrics.histogram('latency_ms', duration, { region: 'us' });
```

The metrics are per-region.

## Verification
- **Test:** Geo-routing works
- **Test:** Data is in the right region
- **Test:** Failover works
- **Live:** Latency is monitored
- **Audit:** Annual review of multi-region setup

## Gotchas
- **The "no geo-routing" anti-pattern.** Users in Asia
  have 500ms latency; route them to APAC.
- **The "no data residency" anti-pattern.** EU users'
  data is in US; GDPR violation.
- **The "strong consistency across regions" anti-pattern.**
  Not possible; use eventual consistency.
- **The "no failover plan" anti-pattern.** A region
  outage takes down the app; have a failover.
- **The "no monitoring" anti-pattern.** Without per-region
  monitoring, you can't find the issue.

## Related
- `cloudflare/workers-resource-limits.md`
- `multi-tenant-data-isolation.md`
- `gdpr-article-17-erasure.md`
- `store-region-matrix.md`
- `scaling-strategies-detail.md`
- CF docs: https://developers.cloudflare.com/workers/
- Multi-region: https://blog.cloudflare.com/multi-region/
