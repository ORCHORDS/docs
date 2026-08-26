# error-budget-policy

**Issue:** Defining what to do when the error budget is exhausted or nearly exhausted
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Error budgets are tracked but teams have no formal response plan, leading to continued risky deployments during budget exhaustion.

## Pattern / Solution
Define a tiered policy document:

| Budget remaining | Action |
|-----------------|--------|
| > 50%           | Normal development velocity |
| 25–50%          | Reduce feature work, increase reliability investment |
| 10–25%          | Freeze non-critical releases, focus on reliability |
| < 10%           | Incident response mode, no new deploys without VP approval |
| Exhausted        | Full freeze, post-mortem required before resuming |

Store the policy in the runbook and link from alert notifications.

## Gotchas
- Policy must have named decision-makers, not just job titles
- Distinguish between fast burn (sudden spike) and slow burn (gradual degradation)
- Review the policy quarterly as SLO targets evolve

## Related
- `error-budget-calculation.md`
- `slo-alerting-burn-rate.md`
- `alerting-runbook-linking.md`
