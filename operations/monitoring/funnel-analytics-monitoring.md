# funnel-analytics-monitoring

**Issue:** Tracking conversion funnels to detect drop-off regressions caused by bugs or performance issues
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Conversion rate drops but no error alerts fire. A JS exception or slow page is silently breaking the funnel.

## Pattern / Solution
Instrument each funnel step as an event: page_view, add_to_cart, checkout_start, payment_entered, order_complete. Track step-to-step conversion rates with a 15min rolling window. Alert when any step conversion drops more than 10% below 7-day baseline. Segment by device type, country, and traffic source. Correlate funnel drop with JS error rate and Core Web Vitals degradation.

## Gotchas
Funnel analysis requires session linkage — use persistent anonymous ID, not session ID. Bot traffic inflates top-of-funnel counts — filter by user-agent and behavior patterns. A/B tests can create apparent funnel regressions if not segmented by variant.

## Related
a-b-test-metrics, real-user-monitoring-rum, core-web-vitals-monitoring, sentry-error-tracking
