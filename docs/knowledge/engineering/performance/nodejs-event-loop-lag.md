# nodejs-event-loop-lag

**Issue:** Node.js event loop is blocked, causing request latency spikes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Node.js is single-threaded for JS execution. Any synchronous computation exceeding a few milliseconds blocks all pending requests.

## Pattern / Solution
1. Measure lag: clinic.js doctor or toobusy-js library.\n2. Move CPU-intensive work to Worker Threads or a separate process.\n3. Use streams instead of loading large files into memory.\n4. Avoid synchronous fs calls (readFileSync, existsSync) in request handlers.\n5. Use setImmediate to yield between chunks of work.

## Gotchas
- JSON.parse of large payloads blocks the event loop; parse in a Worker Thread.\n- Regular expressions with catastrophic backtracking can freeze the event loop.\n- Database queries in async/await don't block Node, but await does not resume until the connection pool has a free connection.

## Related
nodejs-profiling-v8, nodejs-worker-threads, database-query-performance, connection-pool-sizing
