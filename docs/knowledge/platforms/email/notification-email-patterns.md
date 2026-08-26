# notification-email-patterns

**Issue:** Designing notification emails that inform without overwhelming
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Product notifications (comment mentions, assignment, status change) need to be useful without causing email fatigue.

## Pattern / Solution
Notification strategies:
1. **Immediate:** Time-sensitive (assigned to you, @mentioned) — send at event time.
2. **Batched:** Lower-priority updates — digest every 4 hours or daily.
3. **Threshold:** Send only after N events (don't email for every single comment).

Digest pattern:
```js
// Batch notifications per user per period
await notificationQueue.add('batch', { userId, event }, {
  delay: 4 * 60 * 60 * 1000,
  deduplication: { id: `notif-${userId}-4h` }
});
```

Email structure:
- Sender name: "[Name] via [Product]" for social triggers.
- One primary action (view, reply) — don't offer 5 options.
- Link directly to the relevant item, not to the dashboard root.

## Gotchas
- Users who prefer in-app notifications should be able to disable email notifications per type.
- Never send notification emails during user's sleep hours; respect timezone.
- Notification emails from social activity (comments, likes) have very short useful windows.

## Related
- email-preference-center, email-frequency-capping, triggered-email-patterns, email-fatigue-prevention
