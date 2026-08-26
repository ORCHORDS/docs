# email-a-b-testing

**Issue:** Running A/B tests on email subject lines, content, and timing
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Gut-feel decisions about subject lines, CTAs, and content are replaced by data with proper A/B testing.

## Pattern / Solution
1. Split audience randomly: 20% variant A, 20% variant B, 60% hold for winner.
2. Send A and B simultaneously to control for time-of-day effects.
3. Wait for statistical significance (minimum 24 hours, ideally 48h for opens).
4. Determine winner by primary metric (open rate for subject, click rate for content).
5. Send winner to remaining 60%.

Statistical significance check (p < 0.05):
- Use Chi-square test or Z-test for proportions.
- Libraries: simple-statistics, jStat.

Most ESPs have built-in A/B testing for subject lines.

## Gotchas
- Do not peek at results and stop early; wait for predetermined sample size.
- Test one variable at a time; changing subject and CTA simultaneously is inconclusive.
- Open rate is unreliable due to Apple MPP; prefer click rate as primary metric.
- Segment size must be statistically meaningful; 1000+ recipients per variant minimum.

## Related
- email-subject-line-best-practices, email-analytics-metrics, email-template-versioning, email-open-tracking
