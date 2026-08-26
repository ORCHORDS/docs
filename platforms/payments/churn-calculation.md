# churn-calculation

**Issue:** Calculating customer churn rate and revenue churn rate accurately
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Churn rate varies depending on whether you measure by customer count or revenue, and whether you use beginning-of-period or average subscribers in the denominator.

## Pattern / Solution
Customer churn rate equals customers who churned in the period divided by customers at start of period. Revenue churn rate equals MRR lost to cancellations plus contractions divided by MRR at start of period. For net revenue churn, subtract expansion MRR. Calculate monthly and smooth with a 3-month rolling average.

## Gotchas
Reactivated customers returning after cancellation should not be counted as new customers to avoid masking churn. Cohort churn analysis is more actionable than aggregate churn. A churn rate below 2% monthly is healthy for SaaS.

## Related
mrr-arr-calculation, ltv-calculation, subscription-metrics-tracking, stripe-cancellation-flow
