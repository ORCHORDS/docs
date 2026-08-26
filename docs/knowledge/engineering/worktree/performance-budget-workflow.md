# performance-budget-workflow

**Issue:** Performance degrades gradually across sprints because no one owns it and there's no agreed baseline
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The app loads in 1.2s at launch. Six months later it's 3.8s. Each PR added "just a small library." No single PR broke anything — the death was by a thousand cuts.

## Pattern / Solution
A performance budget is a set of quantified limits that CI enforces on every PR.

**Define the budget (web example):**
```yaml
performance_budget:
  time_to_interactive: 3000ms      # p75, 3G mobile
  total_blocking_time: 300ms
  largest_contentful_paint: 2500ms
  javascript_bundle_size: 200kb    # gzipped
  image_weight: 500kb              # per page
  api_p95_response_time: 500ms     # for critical paths
```

**Enforce in CI:**
- Use Lighthouse CI (`lhci`) for frontend budgets
- Bundle size: `bundlesize`, `size-limit`, or `webpack-bundle-analyzer` in CI
- API response time: k6 or Artillery baseline benchmark on each PR

**Workflow:**
1. Measure baseline on main branch
2. Set budget at 10–20% above baseline (room to breathe)
3. CI compares each PR against the budget and comments on the PR with a diff
4. Hard fail if any metric exceeds budget by > 10%
5. To increase a budget limit, requires a team discussion and explicit config change (treated like a decision)

**Performance review cadence:**
- Monthly: review budget adherence trend, tighten or relax as appropriate
- Quarterly: set new goals (e.g. reduce LCP by 200ms)

## Gotchas
- Budgets measured in synthetic lab conditions (Lighthouse) differ from real user metrics — track both
- Image weight budgets need format and dimensions policies (e.g. WebP only, max 1200px wide)
- Backend latency budgets vary by endpoint criticality; don't apply one budget to all routes

## Related
- `definition-of-done-checklist.md`
- `ci-cd-pipeline-2026.md`
- `shift-left-security-testing.md`
