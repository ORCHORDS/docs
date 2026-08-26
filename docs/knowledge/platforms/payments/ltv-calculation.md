# ltv-calculation

**Issue:** Calculating Customer Lifetime Value to inform acquisition spend and retention investment
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
LTV is commonly miscalculated by ignoring gross margin, using simple averages across heterogeneous customer segments, or failing to account for expansion revenue.

## Pattern / Solution
Simple LTV equals ARPU times Gross Margin divided by Churn Rate. For SaaS: LTV equals MRR per customer times Gross Margin percentage divided by Monthly Churn Rate. Segment by plan, acquisition channel, and cohort for actionable LTV. Use LTV to CAC ratio target of 3 to 1 minimum for a sustainable business.

## Gotchas
LTV is a prediction, not a fact — high churn rates make LTV calculations unreliable. Early-stage companies with limited data should use 12-month LTV, not lifetime LTV. Include expansion revenue in LTV if your product has expansion potential.

## Related
mrr-arr-calculation, churn-calculation, subscription-metrics-tracking
