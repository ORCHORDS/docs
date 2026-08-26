# timeouts-everywhere-no-exceptions

**Issue:** Missing timeouts on external calls allow a slow dependency to exhaust connection pools and freeze the application
**Date:** 2026-08-11
**Status:** documented

## What happened
A new integration with a third-party data provider used the default HTTP client with no timeout configured. The provider's API slowed to a crawl during their maintenance window. Every inbound request to the application spawned a thread waiting indefinitely for the provider. Within minutes, all threads were blocked. The application stopped serving any requests, including those that never touched the provider.

## The lesson
Every network call — HTTP requests, database queries, queue reads, RPC calls — must have an explicit timeout. "No timeout" is not a valid setting. Default library timeouts (often infinite or 30+ seconds) are almost always wrong for production services.

## Why it matters
Without timeouts, a slow dependency becomes an uncapped resource drain. Threads, connections, and memory accumulate until the process runs out. The blast radius extends to every feature, not just the one touching the slow dependency.

## How to apply
- [ ] Audit every HTTP client, database client, and queue client for timeout configuration.
- [ ] Set connect timeout (usually 1-3 s) and read timeout (usually 5-30 s, depending on operation) separately.
- [ ] Set an overall request budget timeout that covers retries (e.g., 10 s total for a downstream call with 2 retries).
- [ ] Add a linter or CI check that flags HTTP client instantiation without explicit timeouts.
- [ ] Test timeout behavior: kill the downstream service in staging and verify your application degrades gracefully within the timeout window.

## Related
- `circuit-breaker-prevents-cascade-failure.md`
- `health-checks-must-check-dependencies.md`
