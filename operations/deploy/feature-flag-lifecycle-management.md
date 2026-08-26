# Feature Flag Lifecycle Management — Types, Platforms, and Cleanup

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your codebase has 200 feature flags, but nobody knows which are still
active. A flag named `new_checkout_flow` was created 18 months ago —
the checkout flow is no longer "new" but the flag is still in the code
with conditional logic wrapping it. A developer removes the flag from
LaunchDarkly but leaves the `if (flag)` checks in code, creating dead
branches that confuse new team members. Another flag was accidentally
left at 50% rollout for 6 months because no one owned the cleanup.

## Context

Feature flags decouple deployment from release, enabling progressive
rollouts, A/B experiments, operational kill switches, and permission-
based access control. In 2026, the major platforms (LaunchDarkly,
Unleash, Flipt) have converged on similar lifecycle models, but the
critical challenge remains flag cleanup — roughly 80% of flag removals
touch more than one file, and stale flags are the leading source of
feature-flag technical debt. Healthy codebases maintain fewer than
20-30 active flags per service.

## Flag types

```
Type             Lifespan        Purpose
────────────────────────────────────────────────────────
Release          Days-weeks      Decouple deploy from release
                                 Delete once fully rolled out
Experiment       Test duration   A/B testing, multivariate
                                 Collapse to winning variant
Ops              Long-lived      Circuit breakers, load shedding
                                 Graceful degradation
Permission       Permanent       Role/license/tier access control
                                 Part of the product
```

## Lifecycle flow

```
Create (with type, owner, expiry date)
  → Develop (feature branch, unit tests wrap flag)
    → Test (staging, canary environments)
      → Roll Out (percentage ramp: 1% → 5% → 25% → 100%)
        → Stabilize (monitor metrics for 1-2 weeks)
          → Clean Up (remove conditional logic + archive flag)

Rollout strategy:
  1%   → internal team (dogfood)
  5%   → beta users / early adopters
  25%  → broader segment, monitor error rates
  50%  → half traffic, compare metrics A/B
  100% → full rollout, begin cleanup countdown
```

## Platform comparison (2026)

```
                LaunchDarkly      Unleash           Flipt
────────────────────────────────────────────────────────────
Lifecycle:      6 stages          5 stages          Manual
Stale detect:   Code References   Stuck-in-Cleanup  N/A
Pricing:        Enterprise        Open-source core  Open-source
Storage:        Cloud             DB-backed         Git-native YAML
Strength:       Mature lifecycle  Self-hosted        GitOps workflow

LaunchDarkly stages:
  Live → Ready for Code Removal → Ready to Archive
  → Archived → Deprecated → Deleted

Unleash stages:
  Define → Develop → Production → Cleanup → Archived
```

## Stale flag detection

```
A flag is stale when:
  → Not updated in 2+ weeks AND disabled in all environments
  → Not updated in 2+ weeks AND 100% traffic to one variation
  → Zero code references found (LaunchDarkly Code References CLI)
  → Passed its expiry date without cleanup

Automated detection:
  # LaunchDarkly Code References (CI integration)
  ld-find-code-refs \
    --accessToken=$LD_ACCESS_TOKEN \
    --projKey=default \
    --repoName=my-app

  # Custom script: find flags with no code references
  for flag in $(ld-api list-flags); do
    refs=$(grep -r "$flag" src/ | wc -l)
    if [ "$refs" -eq 0 ]; then
      echo "STALE: $flag has 0 code references"
    fi
  done
```

## Anti-patterns

- **Not classifying flag type at creation** — without knowing if a
  flag is release vs ops vs permanent, no one knows when to remove
  it. Every flag needs a type and an owner at creation time.
- **Skipping the cleanup phase** — removing the flag from the
  management platform but leaving conditional logic in code (or vice
  versa). Both the flag definition and all code references must be
  removed together.
- **Reusing archived flag names** — Unleash warns this can
  "unintentionally re-enable outdated behavior." Use unique names
  and never recycle archived flag keys.
- **Accumulating too many active flags** — complexity compounds.
  Each flag doubles the number of code paths that need testing.
  Target fewer than 20-30 active flags per service.

## Gotchas

- **Flag coupling** — flags that depend on other flags create
  combinatorial complexity. If flag A and flag B interact, you have
  4 code paths to test (both off, A on, B on, both on). Minimize
  flag interactions.
- **Database migrations behind flags** — rolling back a flag that
  triggered a database schema change is not trivial. Separate
  schema migrations from feature flags — migrations should be
  backward-compatible independently.
- **Testing all flag states** — your test suite should test both
  flag-on and flag-off paths. A common failure is testing only the
  new code path and discovering the old path is broken when the
  flag is turned off in an incident.
- **No owner or expiry date** — flags without accountability become
  permanent fixtures. Assign an owner and a cleanup date at creation.
  Alert when the expiry date passes without cleanup.

## Verification

- Every flag has a type, owner, and expiry date at creation.
- Stale flag detection runs weekly (automated scan).
- Active flag count per service stays below 30.
- Flag cleanup removes both platform definition and code references.
- Rollout follows graduated percentage ramp with monitoring.
- Test suite covers both flag-on and flag-off paths.

## Related

- `documentation/categories/lessons/feature-flag-lifecycle-management.md`
- `documentation/categories/deploy/progressive-canary-deployment-rollback.md`
- `documentation/categories/testing/chaos-engineering-fault-injection.md`

## Source URLs (verified 2026-08-16)

- Feature Flag Rollout Strategies 2026: Engineering Guide — https://www.digitalapplied.com/blog/feature-flag-rollout-strategies-2026-engineering-playbook
- 4 Types of Feature Flags, Challenges, and Best Practices — https://octopus.com/devops/feature-flags/
- The Engineer's Guide to Feature Flag Technical Debt — https://www.growthbook.io/blog/engineering-guide-feature-flag-technical-debt
- Open Source Feature Flag Tools Compared 2026 — https://flagshark.com/blog/open-source-feature-flag-tools-compared-2026/
