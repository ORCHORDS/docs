# triggered-email-patterns

**Issue:** Sending emails in response to specific user actions or system events
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Triggered emails (password reset, purchase confirmation, feature adoption nudge) are the highest-engagement email type.

## Pattern / Solution
Event-driven pattern:
```js
// Emit event
eventBus.emit('user.signed_up', { userId, email, name });

// Handler
eventBus.on('user.signed_up', async ({ userId, email, name }) => {
  await emailQueue.add('send', { to: email, template: 'welcome', data: { name } });
  await drip.enroll(userId, 'onboarding-sequence');
});
```

Common triggers:
- `user.signed_up` -> welcome email
- `user.trial_ending` -> upgrade nudge (3 days before)
- `invoice.created` -> invoice email
- `payment.failed` -> dunning email
- `user.inactive` -> re-engagement (30 days no login)

## Gotchas
- Idempotency: emit events exactly-once or deduplicate at handler level.
- Delay some triggers by a few minutes to avoid race conditions with DB writes.
- Test all triggers in staging before production; triggered email bugs are hard to notice.
- Some triggers fire thousands of events simultaneously (batch import); throttle email sends.

## Related
- drip-campaign-architecture, email-queue-architecture, welcome-email-sequence, re-engagement-campaign
