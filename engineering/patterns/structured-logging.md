# structured-logging

**Issue:** Why structured logging beats free-form
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your logs are strings: `console.log("User u_123 logged in at 3pm from 192.168.1.1")`. You want to find "all logins from a specific IP." You grep for the IP. The result is mixed in with other messages. You wish you had a database.

## Root cause
**Free-form logs are write-only.** You can write them, but
querying them is regex hell. Structured logs are queryable.

**Source:** Stripe — Structured Logging:
https://stripe.com/blog/structured-logging

> "A structured log event is one that has been formatted so
> that it can be reliably parsed and queried."

## Free-form vs structured

```ts
// ❌ Free-form: hard to query
console.log("User u_123 logged in at 3pm from 192.168.1.1");
console.log(`Login failed for u_${userId}: wrong password`);

// ✅ Structured: queryable
console.log({
  level: 'info',
  message: 'user.login',
  userId: 'u_123',
  ip: '192.168.1.1',
  timestamp: '2026-08-09T15:00:00Z',
});

console.log({
  level: 'warn',
  message: 'user.login.failed',
  userId: 'u_123',
  reason: 'wrong_password',
  timestamp: '2026-08-09T15:00:00Z',
});
```

In Datadog / CloudWatch / Honeycomb:
- `level:info message:user.login` → all logins
- `level:warn message:user.login.failed` → all failed logins
- `userId:u_123` → all events for user 123
- `ip:192.168.1.1` → all events from IP

## The log schema

Every log line should have:
- **`timestamp`** — when the event happened (ISO 8601)
- **`level`** — `debug`, `info`, `warn`, `error`, `fatal`
- **`message`** — the event name (e.g. `user.login`)
- **`service`** — which service emitted it
- **`traceId`** — the trace correlation ID
- **`spanId`** — the current span ID (if any)
- **`tenantId`, `userId`** — the context (if applicable)
- **Event-specific fields** — everything else

```ts
const logContext = {
  service: 'example project-api',
  traceId: currentTraceId,
  spanId: currentSpanId,
  tenantId: ctx.tenant.id,
  userId: ctx.user.id,
};

function logEvent(message: string, level: 'debug' | 'info' | 'warn' | 'error' = 'info', fields: Record<string, unknown> = {}): void {
  console.log(JSON.stringify({
    timestamp: new Date().toISOString(),
    level,
    message,
    ...logContext,
    ...fields,
  }));
}

// Usage
logEvent('user.login', 'info', { ip: '192.168.1.1', userAgent: '...' });
logEvent('payment.failed', 'error', { amount: 100, error: err.message });
```

## Log levels

| Level | When |
|---|---|
| `debug` | Verbose info for debugging; off in production |
| `info` | Normal operation: "user signed up" |
| `warn` | Something unexpected but handled: "login failed" |
| `error` | Something failed: "payment failed" |
| `fatal` | The system is in trouble: "DB unreachable" |

## What to log

✅ Log:
- **State changes** (user.created, post.deleted, payment.completed)
- **Auth events** (login, logout, failed login, password reset)
- **External calls** (vendor API call + response code)
- **Errors** (with full context)
- **Slow operations** (p95+ latencies)

❌ Don't log:
- **PII** (email, phone, name, IP for some jurisdictions)
  → use a hash or a reference ID
- **Secrets** (API keys, tokens, passwords)
- **High-frequency events without aggregation** (every API
  call to a hot path)
- **Free-form data** (untrusted input — see
  `log-injection-prevention.md`)

## Log volumes and sampling

For a 1000-RPS app:
- **1 log per request** = 86M logs/day
- **Storage cost:** $0.50-$2/GB/month in cloud log services
- **Query cost:** based on data scanned, often $5/TB

For high-volume apps, **sample**:
- 1-10% of normal traffic
- 100% of errors
- 100% of slow requests (p95+)
- 100% of security events (auth, etc.)

```ts
function shouldLog(level: string, durationMs: number): boolean {
  if (level === 'error' || level === 'fatal') return true;
  if (durationMs > 1000) return true;  // Slow
  if (Math.random() < 0.1) return true;  // 10% sample
  return false;
}
```

## Log aggregation

Three main options:
1. **CF Logpush** → R2 / Datadog / Splunk
2. **Direct log shipping** to a third party (Datadog,
   Honeycomb, etc.)
3. **Custom log pipeline** (e.g. Vector, Loki)

For CF Workers, Logpush is the standard:
```toml
[[logpush]]
destination = "r2"
dataset = "production_logs"
```

## Verification
- **Test:** `test/logging.test.ts > logs are valid JSON with
  required fields` — passes
- **Live:** Log volume is monitored; alerts on anomaly
- **Audit:** Quarterly review of log schema + retention

## Gotchas
- **The log schema is a contract.** Changes break downstream
  queries. Use versioned names if you change the schema.
- **PII in logs is a compliance issue.** A log file with
  1M user emails is a leak. Hash user IDs.
- **The log level is not the alert level.** A `warn` log may
  trigger an alert; an `error` log may not. Configure the
  alert in your log aggregator, not in the app.
- **Console.log in Workers is not async.** It writes
  synchronously to the worker's stdout. For high-volume
  logging, use a buffered log shipper.
- **CF Workers console.log has a 1KB line limit.** For longer
  output, split or truncate.

## Related
- `log-injection-prevention.md`
- `observability-three-pillars.md`
- `tracing-vs-logging.md`
- Stripe: https://stripe.com/blog/structured-logging
- 12-factor app logs: https://12factor.net/logs
