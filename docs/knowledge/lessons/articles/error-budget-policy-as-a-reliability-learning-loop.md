# Error-budget policy as a reliability learning loop

**Issue:** Teams often treat an SLO breach as an incident metric and then resume feature work without changing priorities. An error-budget policy turns measured user impact into a pre-agreed decision rule, so reliability work is neither punitive nor endlessly deferred.

**Date:** 2026-08-17
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The lesson

An error budget is the allowed failure implied by an SLO over a defined window. The operational value comes from a policy that all relevant stakeholders accept before the budget is exhausted.

1. **Agree the measurement first.** Define the indicator, population, window, exclusions, data source, and owner. A budget cannot settle prioritization if teams dispute what is being counted.
2. **Pre-commit the response.** State what changes when the budget is healthy, approaching exhaustion, exhausted, or consumed by a single major incident. Include permissible exceptions such as urgent security fixes.
3. **Use misses to improve the system.** A budget burn should trigger root-cause learning: dependency resilience, test gaps, rollback quality, capacity, alert classification, and missing safeguards—not blame.
4. **Make tradeoffs visible.** Product, engineering, and reliability owners must jointly approve the policy. This is how an SLO becomes a decision instrument rather than a dashboard ornament.
5. **Revisit inputs with evidence.** Adjust an SLO or policy only through an explicit review of user impact and capacity; do not quietly redefine the indicator after a miss.

## Minimal policy evidence

- SLO, error-budget calculation, window, and in-scope traffic.
- Release/change rules for each budget state.
- Named exception authority and expiry for exceptions.
- Incident/post-incident actions tied to budget consumption.
- A periodic review record showing whether the policy changed and why.

## Anti-patterns

- **Automatic release freezes with no exception process:** emergency remediation may become slower and riskier.
- **No consequence after exhaustion:** the “budget” is not a control if priorities never change.
- **Counting only convenient telemetry:** unmeasured user failures produce false confidence.
- **Using the policy to punish individuals:** it suppresses reporting and loses the learning signal.

## Sources

- [Google SRE Workbook: Example Error Budget Policy](https://sre.google/workbook/error-budget-policy/)
- [Google SRE Workbook: implementing SLOs and continuous improvement](https://sre.google/workbook/implementing-slos/)
