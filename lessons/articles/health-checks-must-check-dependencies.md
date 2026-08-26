# health-checks-must-check-dependencies

**Issue:** Health checks that only verify the process is alive mislead load balancers into sending traffic to broken instances
**Date:** 2026-08-11
**Status:** documented

## What happened
A service's health endpoint returned 200 as long as the process was running. The database connection pool was exhausted due to a connection leak. The process was alive; the service could not serve any requests. The load balancer kept routing traffic to the broken instances because the health check passed. Users saw errors while ops saw "all instances healthy."

## The lesson
A health check must verify that the instance can actually serve requests. This means checking critical dependencies: can it open a database connection, can it reach required downstream services, is its connection pool healthy? A process that is up but cannot serve traffic is not healthy.

## Why it matters
Load balancers and orchestrators (Kubernetes, ECS) use health checks to route traffic. A health check that lies produces a situation where the monitoring says green and users see errors — the worst possible combination for diagnosing and fixing an outage.

## How to apply
- [ ] Implement `/health/live` (is the process alive — check: returns 200) and `/health/ready` (can it serve traffic — check: dependencies).
- [ ] In the readiness check, test database connectivity with a lightweight query (e.g., `SELECT 1`).
- [ ] Check connection pool saturation — fail ready if pool usage > 90%.
- [ ] Set a timeout on the health check itself (e.g., 5 s) so a slow dependency doesn't cause the check to hang.
- [ ] Use the readiness check for load balancer routing; use the liveness check for restart decisions.

## Related
- `circuit-breaker-prevents-cascade-failure.md`
- `timeouts-everywhere-no-exceptions.md`
- `monitor-before-and-after-deploy.md`
