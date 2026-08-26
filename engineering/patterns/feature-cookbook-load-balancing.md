# feature-cookbook-load-balancing

**Issue:** Load balancing — round-robin, least-conn, weighted
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your single API server is at 100% CPU. You add a second
server. You put a load balancer in front. The first
server still gets 90% of the traffic. The second is
idle. You wonder why.

## Root cause
**Default load balancing is often round-robin DNS.** Use
a proper LB.

**Source:** AWS ELB docs.

## Load balancing strategies

### Round-robin
- **How:** Each request goes to the next server
- **Pros:** Simple, fair
- **Cons:** Doesn't account for server load

### Least-connections
- **How:** Send to the server with the fewest
  connections
- **Pros:** Adapts to actual load
- **Cons:** Slightly more complex

### Weighted
- **How:** Each server gets a weight (proportion of
  traffic)
- **Pros:** Can handle heterogeneous servers
- **Cons:** Manual tuning

### IP hash
- **How:** Hash the client IP to determine the server
- **Pros:** Same client goes to same server
- **Cons:** Bad if one server is overloaded

### Random
- **How:** Random server
- **Pros:** Simple, works for homogeneous
- **Cons:** Doesn't adapt to load

## The "CF load balancer" pattern

For CF, use the load balancer:
```ts
// Origin pool
const pool = [
  { address: 'app-us-east-1.example.com', weight: 1 },
  { address: 'app-us-east-2.example.com', weight: 1 },
  { address: 'app-us-west-1.example.com', weight: 0.5 },
];

// Geo-steering: route by user location
const geoRouting = {
  US: 'us-east',
  EU: 'eu-west',
  ASIA: 'asia-east',
};
```

CF handles the load balancing + geo-routing.

## The "CF health check" pattern

For health checks:
```ts
// CF checks the origin every 30s
const healthCheck = {
  path: '/health',
  expectedCodes: [200],
  interval: 30,  // seconds
  timeout: 5,
};
```

A failed health check removes the origin.

## The "sticky session" pattern

For sticky sessions (same client → same server):
```ts
// Use a cookie
response.headers.set('set-cookie', `lb=${serverId}; path=/`);
```

A cookie is sent to the same server.

**Source:** MDN — Set-Cookie:
https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie

## The "weighted" pattern

For weighted load balancing:
```ts
// 70% to new server, 30% to old
const weighted = [
  { address: 'new.example.com', weight: 0.7 },
  { address: 'old.example.com', weight: 0.3 },
];
```

Weighted allows gradual migration.

## The "circuit breaker" pattern

For a failing origin, the LB stops sending traffic:
```ts
// CF: if origin fails 3 times in 60s, mark unhealthy
const circuitBreaker = {
  failureThreshold: 3,
  resetTimeout: 60,
};
```

A failing origin is taken out of rotation.

## The "canary deploy" pattern

For canary, send 5% of traffic to the new version:
```ts
const canary = [
  { address: 'new.example.com', weight: 0.05 },  // Canary
  { address: 'stable.example.com', weight: 0.95 },
];
```

A small percentage tests the new version.

## The "blue-green deploy" pattern

For blue-green, switch 100% at once:
```ts
// Phase 1: stable
const phase1 = [{ address: 'blue.example.com', weight: 1 }];

// Phase 2: green
const phase2 = [{ address: 'green.example.com', weight: 1 }];
```

Instant switch; instant rollback.

## The "geo-steering" pattern

For geo, route to the closest region:
```ts
// US traffic → US origin
// EU traffic → EU origin
// Asia traffic → Asia origin
const geoRouting = {
  'NA': 'us-east',
  'EU': 'eu-west',
  'AS': 'asia-east',
};
```

Lower latency + data residency.

## The "failover" pattern

For failover, the backup origin:
```ts
// Primary + backup
const failover = {
  primary: 'app.example.com',
  backup: 'app-backup.example.com',
};
```

If primary is down, backup takes over.

## The "connection draining" pattern

For graceful shutdown, drain connections:
```ts
// Server shutdown:
async function drainAndShutdown(server: Server): Promise<void> {
  // 1. Stop accepting new connections
  server.close();

  // 2. Wait for in-flight requests (max 30s)
  await Promise.race([
    server.drain(),
    sleep(30_000),
  ]);

  // 3. Shutdown
  process.exit(0);
}
```

Drain = no failed requests.

## The "load balancer anti-pattern" anti-patterns

### 1. DNS round-robin
- **Issue:** Doesn't account for server load
- **Fix:** Use a proper LB (CF, AWS, GCP)

### 2. No health check
- **Issue:** Traffic goes to a dead server
- **Fix:** Health check every 30s

### 3. No sticky session
- **Issue:** Session state is lost
- **Fix:** Use cookies (only if needed)

### 4. No failover
- **Issue:** Single origin = single point of failure
- **Fix:** Multiple origins + failover

### 5. No graceful shutdown
- **Issue:** In-flight requests are killed
- **Fix:** Drain connections before shutdown

## Verification
- **Test:** Load balancer distributes traffic
- **Test:** Health check works
- **Test:** Failover works
- **Live:** Latency is monitored
- **Audit:** Annual review of LB config

## Gotchas
- **The "DNS round-robin" anti-pattern.** Use a proper
  LB.
- **The "no health check" anti-pattern.** Dead servers
  stay in rotation.
- **The "no failover" anti-pattern.** Single origin = no
  resilience.
- **The "no graceful shutdown" anti-pattern.** In-flight
  requests are killed.

## Related
- `feature-cookbook-multi-region.md`
- `feature-cookbook-disaster-recovery.md`
- `scaling-cf-workers.md`
- `safe-deploy-checklist.md`
- `zero-downtime-deploys.md`
- `scaling-strategies-detail.md`
- CF load balancer: https://developers.cloudflare.com/load-balancing/
