# subscription-metrics-tracking

**Issue:** Tracking key subscription health metrics: trial conversion, activation, and retention
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Without granular subscription event tracking, it is impossible to identify where users drop off in the trial-to-paid funnel or which cohorts have the worst retention.

## Pattern / Solution
Emit analytics events at each lifecycle stage: trial_started, trial_converted, trial_expired, subscription_activated, subscription_cancelled, payment_failed, payment_recovered. Include plan, amount, source, and user properties. Use Mixpanel, Amplitude, or Segment to compute funnel conversion rates and cohort retention.

## Gotchas
Do not rely solely on Stripe webhooks for analytics — Stripe does not provide funnel or cohort views. Track time-to-first-charge for trial conversions to optimize the trial length. Payment failure recovery rate is a key metric often overlooked.

## Related
mrr-arr-calculation, churn-calculation, ltv-calculation, payment-analytics-dashboard
