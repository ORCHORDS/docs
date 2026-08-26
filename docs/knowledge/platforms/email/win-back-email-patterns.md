# win-back-email-patterns

**Issue:** Bringing back churned or cancelled customers with targeted email campaigns
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cancelled customers have purchase intent data and product familiarity; win-back emails convert at higher rates than cold outreach.

## Pattern / Solution
Timing: 3 days, 30 days, 90 days post-cancellation.

Email 1 (Day 3): Address the specific reason for cancellation if captured:
```js
const subject = cancellationReason === 'too-expensive'
  ? "We've heard you - here's 30% off to come back"
  : "We'd love to have you back";
```

Email 2 (Day 30): Feature update — "Here's what's changed since you left."

Email 3 (Day 90): Final offer with expiry urgency.

Best practices:
- Personalize with cancellation reason.
- Show what's improved or what they're missing.
- Time-limited discount with real expiry enforced in backend.

## Gotchas
- Only email users who have given ongoing marketing consent (GDPR applies post-cancellation).
- Do not send win-back to users who explicitly opted out at cancellation.
- Cap win-back sequence; repeated emails to non-responders damage reputation.

## Related
- re-engagement-campaign, churn-prevention-emails, email-preference-center, gdpr-email-consent
