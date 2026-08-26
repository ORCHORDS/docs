# email-analytics-metrics

**Issue:** Understanding and interpreting key email analytics metrics
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Raw metrics without context lead to wrong decisions; understanding what each metric means and its limitations is critical.

## Pattern / Solution
| Metric | Formula | Benchmark | Reliability |
|---|---|---|---|
| Delivery rate | Delivered / Sent | >98% | High |
| Open rate | Unique opens / Delivered | 20-40% | Low (Apple MPP) |
| Click rate | Unique clicks / Delivered | 2-5% | Medium |
| Click-to-open | Clicks / Opens | 15-25% | Medium |
| Bounce rate | Bounces / Sent | <2% | High |
| Complaint rate | Complaints / Delivered | <0.08% | High |
| Unsubscribe rate | Unsubs / Delivered | <0.5% | High |
| Revenue per email | Revenue / Sent | Industry varies | High |

Primary health KPIs: bounce rate, complaint rate, unsubscribe rate.
Primary engagement KPIs: click rate, conversion rate, revenue per email.

## Gotchas
- Open rate as a metric is increasingly unreliable post-Apple MPP; do not use for A/B test outcomes.
- Benchmarks vary significantly by industry and audience; compare to your own historical baseline.
- Complaint rate visible in Google Postmaster Tools may lag by 24-48 hours.

## Related
- email-open-tracking, email-click-tracking, email-a-b-testing, email-roi-measurement
