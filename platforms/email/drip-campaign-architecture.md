# drip-campaign-architecture

**Issue:** Building automated email drip campaigns triggered by user events
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Onboarding sequences, nurture tracks, and trial conversions require time-based multi-step email automation.

## Pattern / Solution
Data model:
```sql
CREATE TABLE drip_campaigns (id, name, trigger_event TEXT);
CREATE TABLE drip_steps (id, campaign_id, step_number, delay_hours, template_slug);
CREATE TABLE drip_enrollments (
  id, campaign_id, user_id, current_step,
  next_send_at, status
);
```

Enrollment:
```js
async function enroll(userId, campaignId) {
  const [firstStep] = await getSteps(campaignId);
  await db.insert('drip_enrollments', {
    userId, campaignId, currentStep: 1,
    nextSendAt: addHours(new Date(), firstStep.delayHours)
  });
}
```

Worker: runs every minute, finds due enrollments, sends email, advances step or completes.

Exit conditions: unsubscribe, goal conversion, manual removal.

## Gotchas
- Re-enrollment logic: should users re-enter a campaign if they trigger the event again? Default: no.
- Campaign changes must not affect in-progress enrollments unless explicitly desired.
- Segment exit: if user's attributes change mid-campaign (e.g., upgrades), exit them automatically.
- Always respect suppression list even mid-sequence.

## Related
- triggered-email-patterns, email-scheduling-patterns, welcome-email-sequence, onboarding-email-sequence
