# churn-prevention-emails

**Issue:** Sending targeted emails to at-risk users before they cancel
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Proactive intervention when users show disengagement signals is more effective than post-cancellation win-back.

## Pattern / Solution
Churn signals:
- Login frequency drops (2+ weeks no login after being active).
- Key feature usage stops.
- Support tickets about cancellation process.
- Billing failure (payment-failed email).

Trigger:
```js
eventBus.on('user.churn_risk_detected', async ({ userId, signal }) => {
  const template = {
    'no-login': 'churn-prevention-reactivation',
    'payment-failed': 'dunning-retry',
    'cancellation-page-visited': 'save-offer',
  }[signal];
  await emailQueue.add('send', { userId, template });
});
```

Offer escalation: free extension -> discount -> plan downgrade offer.

## Gotchas
- Do not trigger churn prevention on users who just signed up (expected low activity initially).
- Payment failure emails have strict timing requirements; retry windows matter for SaaS billing.
- Sending too many "we noticed you haven't logged in" emails to active users is a support issue.

## Related
- re-engagement-campaign, win-back-email-patterns, triggered-email-patterns, onboarding-email-sequence
