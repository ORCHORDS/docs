# health-check-endpoint

**Issue:** Designing a /healthz endpoint that actually works
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have a `/healthz` endpoint that returns 200 always. The
load balancer is happy. The DB is down. The app shows errors
to users. The `/healthz` is a lie.

## Root cause
**A health check that always returns 200 is not a health check.**
It's a "the server is running" check, which is trivially true
for any server.

**Source:** Google SRE book — Health checks:
https://sre.google/sre-book/load-balancing-datacenter/

> "Health checks are critical to ensure that user requests
> are not routed to unhealthy backends. ... A health check
> should verify that the backend can actually serve user
> requests."

## The 3 levels of health check

### Level 1: Liveness (`/healthz`)
- **What:** "The process is alive"
- **Checks:** The endpoint responds at all
- **Use when:** Kubernetes liveness probe, basic monitoring
- **Example:** `return new Response('OK')` (200 always)

```ts
export async function liveness(request: Request, env: Env): Promise<Response> {
  return new Response('OK', { status: 200 });
}
```

### Level 2: Readiness (`/readyz`)
- **What:** "The process is ready to serve user requests"
- **Checks:** Dependencies are reachable (DB, vendor APIs)
- **Use when:** Kubernetes readiness probe, load balancer
- **Example:** check D1 + vendor API + cache

```ts
export async function readiness(request: Request, env: Env): Promise<Response> {
  const checks = await Promise.all([
    checkD1(env),
    checkVendorAPI(env),
    checkKV(env),
  ]);

  const allOk = checks.every(c => c.ok);
  const status = allOk ? 200 : 503;
  const body = {
    status: allOk ? 'ready' : 'not_ready',
    checks: checks.map(c => ({ name: c.name, ok: c.ok, error: c.error })),
  };

  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

async function checkD1(env: Env): Promise<{ name: string; ok: boolean; error?: string }> {
  try {
    await env.DB!.prepare('SELECT 1').first();
    return { name: 'd1', ok: true };
  } catch (err) {
    return { name: 'd1', ok: false, error: String((err as Error).message) };
  }
}
```

### Level 3: Deep health (`/healthz/deep`)
- **What:** "Everything is working end-to-end"
- **Checks:** Read from DB, fetch from vendor, verify the
  response is correct (not just reachable)
- **Use when:** Manual debugging, scheduled deep checks
- **Example:** read a known record from the DB, verify the
  value

```ts
export async function deepHealth(request: Request, env: Env): Promise<Response> {
  const checks = {
    d1: {
      ok: false,
      latencyMs: 0,
      sample: null as any,
      error: null as string | null,
    },
    // ...
  };

  const d1Start = Date.now();
  try {
    const result = await env.DB!.prepare(
      `SELECT id FROM users LIMIT 1`
    ).first<{ id: string }>();
    checks.d1.ok = !!result;
    checks.d1.sample = result;
  } catch (err) {
    checks.d1.error = String((err as Error).message);
  }
  checks.d1.latencyMs = Date.now() - d1Start;

  // ... more checks

  const allOk = Object.values(checks).every(c => c.ok);
  return new Response(JSON.stringify({
    status: allOk ? 'healthy' : 'unhealthy',
    checks,
  }), { status: allOk ? 200 : 503, headers: { 'content-type': 'application/json' } });
}
```

## What NOT to check

❌ **Don't check vendor APIs in the readiness check.** If a
vendor is down, your readiness check fails, and the load
balancer takes you out of rotation. Now you can't serve any
requests. The user is worse off.

✅ **Check critical dependencies:** the DB, your primary
vendor, your auth service.

❌ **Don't check in liveness that could fail intermittently.**
Liveness is a "kill the pod" check. It should be very rarely
false-positive. If liveness fails, the orchestrator restarts
the instance.

✅ **Use readiness for "I can't serve traffic right now."**
Use liveness for "I'm deadlocked; restart me."

## Caching the health check

For expensive health checks (multiple DB queries, vendor
calls), cache the result:
```ts
let cachedHealth: { status: number; body: string; expiresAt: number } | null = null;

export async function readiness(request: Request, env: Env): Promise<Response> {
  if (cachedHealth && cachedHealth.expiresAt > Date.now()) {
    return new Response(cachedHealth.body, { status: cachedHealth.status, headers: { 'content-type': 'application/json' } });
  }

  // ... do the actual check ...

  cachedHealth = {
    status: result.status,
    body: JSON.stringify(body),
    expiresAt: Date.now() + 5000,  // 5 second cache
  };

  return new Response(cachedHealth.body, { status: result.status, headers: { 'content-type': 'application/json' } });
}
```

This prevents the health check itself from being a load on
the system.

## Verification
- **Test:** `test/health.test.ts > /healthz returns 200,
  /readyz returns 200 with DB up, 503 with DB down` — passes
- **Live:** The load balancer is configured to use /readyz
- **Audit:** Quarterly review of what /readyz checks

## Gotchas
- **The health endpoint is a target.** A motivated attacker
  will hit /readyz to learn about your dependencies. Don't
  expose sensitive info (e.g. "Stripe is down" → attacker
  knows to use a different attack vector).
- **The health check should be idempotent.** Hitting it
  repeatedly should not cause side effects.
- **The cache should expire.** Otherwise the health check
  reports stale "healthy" after a real outage.
- **For CF Workers, the health check is per-isolate.** If you
  have 1000 isolates, you have 1000 health checks. Use a
  shared health check (e.g. a DO that aggregates).

## Related
- `observability-three-pillars.md`
- `error-budget-slo.md` (SLOs use health checks)
- `feature-environment-promotion.md` (per-env health checks)
- Google SRE: https://sre.google/sre-book/load-balancing-datacenter/
- K8s health checks: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
