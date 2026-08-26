# rollbar-vs-sentry

**Issue:** Choosing between Rollbar and Sentry for error monitoring
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams evaluate error tracking tools and need a clear comparison before committing.

## Pattern / Solution
| Feature                | Sentry                     | Rollbar                     |
|------------------------|----------------------------|-----------------------------|
| Performance tracing    | Yes (APM built-in)         | Limited (basic only)        |
| Session replay         | Yes                        | No                          |
| Source maps            | Yes                        | Yes                         |
| Grouping algorithm     | Fingerprinting + AI        | Fingerprinting              |
| Self-hosting           | Yes (Docker, Kubernetes)   | No                          |
| Free tier              | 5k errors/month            | 5k errors/month             |
| Log correlation        | Yes                        | Partial                     |
| Cron monitoring        | Yes                        | No                          |

Recommendation:
- Use **Sentry** for full-stack observability with APM, session replay, and self-hosting needs
- Use **Rollbar** for lightweight error tracking with excellent deploy tracking and a simpler UI

## Gotchas
- Both tools have SDK overhead; benchmark before adding to hot paths
- Sentry self-hosting requires significant infrastructure (PostgreSQL, Redis, Kafka)
- Neither is a replacement for structured logging

## Related
- `sentry-error-tracking.md`
- `honeycomb-observability.md`
