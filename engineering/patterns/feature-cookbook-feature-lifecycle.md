# feature-cookbook-feature-lifecycle

**Issue:** Feature lifecycle — discovery, design, launch, sun-set
**Date:** 2026-08-09
**Status:** documented

## Symptom
You build features. Some are popular. Some are not.
You don't know which. You keep building the wrong
things. You wish you had a process.

## Root cause
**Without a lifecycle, features drift.** Use a
structured lifecycle.

**Source:** Various product guides.

## Stages

1. **Discovery:** Identify the user problem
2. **Design:** Plan the solution
3. **Build:** Implement
4. **Test:** Verify
5. **Launch:** Roll out
6. **Measure:** Track metrics
7. **Iterate:** Improve based on data
8. **Sunset:** Remove if no longer useful

## The "discovery" stage

For discovery:
- **User interviews:** Talk to 5-10 users
- **Surveys:** Quantitative feedback
- **Analytics:** What are users doing?
- **Support tickets:** What are the pain points?
- **Competitor analysis:** What are they doing?

A clear problem statement is the goal.

## The "design" stage

For design:
- **PRD (Product Requirements Doc):** What are we
  building?
- **Wireframes:** How does it look?
- **Tech design:** How will it be built?
- **Edge cases:** What can go wrong?
- **Trade-offs:** What did we choose?

A clear design is the goal.

## The "build" stage

For build:
- **Branch:** Feature branch
- **Tests:** Unit + integration
- **Code review:** Reviewed before merge
- **CI:** Tests + lint + typecheck
- **Deploy:** To staging

A working feature is the goal.

## The "test" stage

For test:
- **Unit tests:** Cover the logic
- **Integration tests:** Cover the flow
- **E2E tests:** Cover the user flow
- **Load tests:** Cover the scale
- **Security tests:** Cover the threat model

A tested feature is the goal.

## The "launch" stage

For launch:
- **Feature flag:** Gradual rollout
- **Internal users:** Dogfood first
- **Beta users:** Small group
- **GA:** General availability
- **Comms:** Announce

A controlled launch is the goal.

## The "measure" stage

For measure:
- **Adoption:** How many users use it?
- **Engagement:** How often?
- **Retention:** Do they come back?
- **Satisfaction:** NPS, surveys
- **Performance:** Latency, errors

A measured feature is the goal.

## The "iterate" stage

For iterate:
- **User feedback:** What do they want?
- **Data analysis:** What are the trends?
- **A/B tests:** Test variations
- **Bug fixes:** Address issues
- **Improvements:** Polish

A better feature is the goal.

## The "sunset" stage

For sunset:
- **Identify:** Low usage + low value
- **Communicate:** Tell users 30+ days in advance
- **Migrate:** Help users transition
- **Disable:** Turn off the feature
- **Remove:** Delete the code

A clean codebase is the goal.

## The "RICE" prioritization

For prioritizing features:
- **Reach:** How many users does this affect?
- **Impact:** How much does it help them?
- **Confidence:** How sure are we?
- **Effort:** How much work?

Score = (Reach × Impact × Confidence) / Effort.

## The "OKR" framework

For OKRs (Objectives + Key Results):
- **Objective:** What are we trying to achieve?
- **Key Result 1:** Measurable outcome
- **Key Result 2:** Measurable outcome
- **Key Result 3:** Measurable outcome

A clear OKR is the goal.

## The "launch checklist" pattern

For a launch checklist:
- [ ] Tests pass
- [ ] Lint + typecheck pass
- [ ] Documentation updated
- [ ] Monitoring in place
- [ ] On-call notified
- [ ] Feature flag enabled
- [ ] Comms sent
- [ ] Status page updated

The checklist ensures nothing is missed.

## The "kill switch" pattern

For a feature, a kill switch:
```ts
if (await isFeatureEnabled('new_billing', user, env)) {
  return newBillingFlow(user, env);
}
```

A kill switch is a feature flag with a quick off.

## The "feature flag" pattern

For gradual rollout:
```ts
async function isFeatureEnabled(flag: string, user: User, env: Env): Promise<boolean> {
  const config = await getFlagConfig(flag, env);

  // Rollout percentage
  if (!isUserInRollout(user, config.percentage)) return false;

  // Tenant allowlist
  if (config.tenants && !config.tenants.includes(user.tenantId)) return false;

  return true;
}
```

The feature is rolled out gradually.

## The "feature anti-pattern" anti-patterns

### 1. No discovery
- **Issue:** Building the wrong thing
- **Fix:** Talk to users first

### 2. No metrics
- **Issue:** Don't know if it works
- **Fix:** Define the metrics

### 3. No rollback
- **Issue:** Can't undo the launch
- **Fix:** Feature flag + kill switch

### 4. No sun-set
- **Issue:** Old features accumulate
- **Fix:** Quarterly review; remove low-value features

### 5. No docs
- **Issue:** Users don't know how to use it
- **Fix:** Document + tutorial

## Verification
- **Test:** The feature works
- **Test:** The metrics are tracked
- **Live:** Adoption is monitored
- **Audit:** Quarterly feature review

## Gotchas
- **The "no discovery" anti-pattern.** Building the wrong
  thing.
- **The "no metrics" anti-pattern.** Don't know if it
  works.
- **The "no rollback" anti-pattern.** Stuck with a bad
  feature.
- **The "no sun-set" anti-pattern.** Old features
  accumulate.

## Related
- `feature-launch-checklist.md`
- `feature-flags.md`
- `feature-flags-best-practices.md`
- `feature-experimentation.md`
- `feature-observability-pattern.md`
- `feature-cookbook-onboarding.md`
- RICE: https://www.intercom.com/blog/rice-simple-prioritization-for-product-managers/
- OKR: https://www.whatmatters.com/the-book/
