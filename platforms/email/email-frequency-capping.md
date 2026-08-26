# email-frequency-capping

**Issue:** Limiting email frequency per subscriber to prevent fatigue and complaints
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Uncapped email frequency leads to unsubscribes and spam complaints; frequency caps protect engagement quality.

## Pattern / Solution
Cap implementation:
```js
async function canSendEmail(userId, type) {
  const caps = {
    marketing: { count: 3, windowDays: 7 },
    notification: { count: 10, windowDays: 1 }
  };
  const cap = caps[type];
  const recent = await db.count('sent_emails', {
    userId, type,
    sentAt: { gte: subDays(new Date(), cap.windowDays) }
  });
  return recent < cap.count;
}
```

Typical caps:
- Marketing: max 3/week
- Digest: 1/week or 1/day per type
- Transactional: uncapped
- Notification: 10/day, configurable by user

Global fatigue cap: no more than 5 total emails/week per user across all types.

## Gotchas
- Frequency caps must be enforced before queuing, not just before sending.
- Transactional emails (password reset, invoice) must bypass marketing frequency caps.
- Caps should apply per email type, not globally (don't block security alerts due to marketing cap).
- Time windows should use rolling windows, not calendar weeks.

## Related
- email-fatigue-prevention, email-preference-center, notification-email-patterns, email-sunset-policy
