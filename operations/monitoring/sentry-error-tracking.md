# sentry-error-tracking

**Issue:** Integrating Sentry for real-time error monitoring and grouping
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Uncaught exceptions and unhandled promise rejections are invisible in production until users report them.

## Pattern / Solution
```typescript
import * as Sentry from "@sentry/node";

Sentry.init({
  dsn: process.env.SENTRY_DSN,
  environment: process.env.NODE_ENV,
  release: process.env.SERVICE_VERSION,
  sampleRate: 1.0,
  tracesSampleRate: 0.1,
  beforeSend(event, hint) {
    // Filter noise
    if (event.exception?.values?.[0]?.type === "AbortError") return null;
    return event;
  },
  integrations: [
    Sentry.httpIntegration(),
    Sentry.expressIntegration(),
  ],
});

// Capture user context
Sentry.setUser({ id: userId, email: userEmail });

// Manual capture
try {
  riskyOperation();
} catch (err) {
  Sentry.captureException(err, { extra: { orderId } });
  throw err;
}
```

## Gotchas
- `sampleRate` controls error events; `tracesSampleRate` controls performance events
- `beforeSend` runs synchronously; keep it fast
- PII scrubbing: use `sendDefaultPii: false` and configure `denyUrls`

## Related
- `sentry-performance-monitoring.md`
- `sentry-alerts-config.md`
- `sentry-releases.md`
