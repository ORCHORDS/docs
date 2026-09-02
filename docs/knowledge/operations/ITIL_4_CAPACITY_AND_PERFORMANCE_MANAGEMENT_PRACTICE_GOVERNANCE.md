# ITIL 4 Capacity and Performance Management Practice Governance

## Purpose

Govern the ITIL 4 capacity and performance management practice so that service capacity is forecast, provisioned, and tuned deliberately, meeting demand at acceptable cost without both exhausting capacity mid-quarter and paying for idle headroom indefinitely.

## Scope

The practice applies to compute, storage, network, and application-tier capacity for studio services, covering demand forecasting, provisioning lead times, performance tuning, and threshold alerting. It does not cover cost allocation (financial management) or SLO target-setting (SRE practice).

## Workflow

1. Model current demand per service: utilization versus provisioned capacity, at the granularity (node, cluster, tenant, region) where decisions are made.
2. Forecast demand using historical growth plus known business drivers (launches, seasonal patterns, contract changes); document the drivers, not just the curve.
3. Establish minimum headroom thresholds per resource type; breaching a threshold opens a capacity task with an owner and due date.
4. Incorporate provisioning lead time into thresholds so that ordering hardware or negotiating cloud limits is triggered before exhaustion, not after.
5. Tune before scaling: profile the top resource consumers and eliminate waste before purchasing capacity.
6. Review actual-versus-forecast accuracy each cycle and adjust the forecasting method when error persists.
7. Report capacity posture to service owners, including exhaustion risk horizon per critical resource.

## Controls and evidence

- Capacity model per service with demand drivers, headroom thresholds, and exhaustion horizon.
- Forecast-versus-actual review with error analysis and method adjustments.
- Capacity task queue with owners, due dates, and closure evidence.
- Performance tuning records showing what was tuned, what it saved, and what it did not.

## Validation

- Sample one critical service and confirm its exhaustion horizon is current and its headroom threshold has a documented rationale.
- Confirm forecast-versus-actual reviews ran on cadence with method corrections when error exceeded tolerance.
- Confirm no capacity task in the queue is past due without an escalation record.

## Failure correction

- **Capacity exhaustion incident** → restore service, then run a post-incident review of why the forecast and thresholds missed; fix the model, not just the instance.
- **Forecast error persistently high** → change the forecasting method or inputs; document what changed and why.
- **Tuning skipped in favor of purchasing** → require a tuning review sign-off on capacity purchases above the threshold amount.

## Limitations

- Forecasts are wrong; the practice exists to be less wrong, earlier. Exhaustion horizons are estimates, not promises.
- Cloud elasticity shortens lead times but does not eliminate regional or quota-driven exhaustion risk.
- Performance tuning outcomes vary by workload; results from one service do not transfer automatically.

## Scope note

This article is part of the operations leaf and pairs with monitoring and SLO practices. Cross-reference: `infra/capacity-planning-forecasting.md`, `monitoring/capacity-planning-metrics.md`, and `SRE_RELEASE_COORDINATION_ERROR_BUDGET_GOVERNANCE.md`.

## Canonical sources

- AXELOS, *ITIL Foundation, ITIL 4 edition* (2019), capacity and performance management practice: https://www.axelos.com/certifications/itil-service-management
- ITIL 4 Practices — Capacity and Performance Management: https://www.axelos.com/certifications/itil-service-management/itil-4-practices
- Google SRE Book, Chapter 5 — Utilization and Saturation: https://sre.google/sre-book/monitoring-distributed-systems/
- NIST SP 800-34 Rev 1 — Contingency Planning Guide for Federal Information Systems: https://csrc.nist.gov/publications/detail/sp/800-34/rev-1/final
- ISO/IEC 20000-1:2018 — Service management — Requirements: https://www.iso.org/standard/73686.html
