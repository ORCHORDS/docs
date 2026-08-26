# nodejs-cluster-patterns

**Issue:** Node.js process uses only one CPU core
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Node.js is single-threaded. The cluster module forks multiple processes sharing the same port, utilizing multiple CPU cores for I/O-bound workloads.

## Pattern / Solution
1. Use cluster.isPrimary to fork one worker per CPU core.\n2. Use PM2 with cluster mode: pm2 start app.js -i max.\n3. Set worker count to os.cpus().length or slightly more for I/O-heavy workloads.\n4. Implement graceful restart: fork a new worker before killing the old one.

## Gotchas
- Workers don't share memory; in-memory state must move to Redis.\n- Cluster does not help for CPU-bound tasks; use Worker Threads instead.\n- Sticky sessions (WebSockets) require a load balancer configured for affinity.

## Related
nodejs-worker-threads, nodejs-event-loop-lag, connection-pool-sizing
