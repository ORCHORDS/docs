# mrr-arr-calculation

**Issue:** Calculating Monthly Recurring Revenue and Annual Recurring Revenue correctly from subscription data
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
MRR/ARR calculations are inconsistent when annual, monthly, and quarterly plans are mixed, when discounts are applied, or when subscriptions are in trial.

## Pattern / Solution
MRR equals the sum of all active subscriptions normalized to monthly amount. For annual plans, divide by 12. For quarterly, divide by 3. Exclude trial subscriptions with no payment method. Apply coupon discounts to the effective amount. ARR equals MRR times 12. Track new MRR, expansion MRR, contraction MRR, churn MRR, and reactivation MRR separately.

## Gotchas
Do not include one-time charges in MRR. Metered billing adds variable MRR — use prior month actuals or rolling average. Trial periods without cards should not count as MRR.

## Related
churn-calculation, ltv-calculation, subscription-metrics-tracking, revenue-recognition-saas
