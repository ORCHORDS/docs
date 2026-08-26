# notification-system-design

**Issue:** Notifications must be delivered reliably across multiple channels at scale without duplicate delivery
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A user receives the same push notification three times because three retries were all delivered by the provider before the first acknowledgment was processed.

## Pattern / Solution
Persist notification intent before sending. Track delivery state per channel per user. Deduplicate by idempotency key at the delivery layer. Use exponential backoff for retries. Respect user preferences and quiet hours. Route to appropriate channels (push, email, SMS) based on urgency and user settings.

## Gotchas
Push notification providers have their own retry logic and coordinating with application-level retries causes duplicates. Rate limits from providers must be respected. Opt-out preferences must be enforced before reaching the send step.

## Related
idempotency-design, at-least-once-delivery, message-deduplication
