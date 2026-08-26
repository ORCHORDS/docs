# email-roi-measurement

**Issue:** Measuring the revenue impact and ROI of email programs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Email programs need ROI measurement to justify investment and prioritize campaigns.

## Pattern / Solution
Key metrics:
- **Revenue per email (RPE):** Total revenue attributed to email / emails sent.
- **Email-attributed revenue:** Track via UTM parameters + conversion tracking.
- **List value:** RPE x list size x monthly send frequency.
- **ROI:** (Revenue - Cost) / Cost x 100%.

Attribution model:
1. Add UTM parameters to all email links: `utm_source=email&utm_medium=drip&utm_campaign=welcome`.
2. Track conversion events in analytics (GA4, Mixpanel).
3. Apply attribution window (1-day, 7-day, 30-day); shorter windows are more conservative.

Costs to include:
- ESP fees, email tool subscriptions, design and copywriting time.

## Gotchas
- Email revenue is often over-attributed in last-click models; use multi-touch where possible.
- Transactional emails (invoices, confirmations) shouldn't be attributed revenue; the sale already happened.
- List growth cost (acquisition) should be factored into long-term ROI calculations.

## Related
- email-analytics-metrics, email-a-b-testing, email-click-tracking, email-batch-sending
