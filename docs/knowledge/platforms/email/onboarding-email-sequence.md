# onboarding-email-sequence

**Issue:** Designing an onboarding email sequence that drives activation and reduces churn
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Users who don't reach their "aha moment" within the first week are likely to churn; onboarding emails guide them there.

## Pattern / Solution
1. Map activation milestones: profile complete, first project created, team invited, first integration.
2. Trigger emails when users are behind expected progress, not on fixed timers:
```js
if (daysSinceSignup >= 2 && !user.hasCreatedProject) {
  sendEmail(user, 'create-first-project');
}
```
3. Sequence example:
   - Day 0: Welcome + goal-setting
   - Day 2 (if no project): Nudge to create first project
   - Day 4 (if no team): Invite team member prompt
   - Day 7: Progress recap + next steps

4. Stop sequence when user reaches full activation.

## Gotchas
- Progress-based triggers require reliable event tracking; instrument activation events first.
- Do not send "you haven't done X" emails too early; premature urgency is annoying.
- Show concrete benefit in subject line, not just task: "Your first project is one click away" vs. "Create a project".

## Related
- welcome-email-sequence, drip-campaign-architecture, triggered-email-patterns, churn-prevention-emails
