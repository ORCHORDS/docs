# email-personalization-patterns

**Issue:** Implementing effective email personalization beyond first-name substitution
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Basic `Hi {{firstName}}` personalization has diminishing returns; behavioral and contextual personalization drives better engagement.

## Pattern / Solution
Personalization tiers:
1. **Identity:** Name, company, role — minimal lift.
2. **Behavioral:** Last action, purchase history, feature usage — moderate lift.
3. **Predictive:** Recommended content, products, next steps based on ML — highest lift.

Implementation:
```js
const emailData = {
  name: user.firstName,
  lastLogin: formatDate(user.lastLoginAt),
  topFeature: getMostUsedFeature(user.id),
  recommendedPlan: predictUpgradePlan(user),
};
```

Dynamic content blocks: show/hide sections based on user attributes (plan tier, country, behavior).

## Gotchas
- Missing personalization data renders as empty string; always provide fallback values.
- Over-personalization can feel surveillance-y; use with restraint.
- Personalized subject lines have highest open-rate impact when relevant, not just name-based.
- Ensure personalization data is fresh; stale data (e.g., outdated plan name) is worse than generic.

## Related
- email-dynamic-content, liquid-template-email, handlebars-email-templates, email-a-b-testing
