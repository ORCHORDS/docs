# rum-vs-synthetic-metrics

**Issue:** Lab metrics don't match real-user experience
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Synthetic (lab) metrics use controlled conditions. Real User Monitoring (RUM) captures actual user experiences. Both are necessary: synthetic for debugging, RUM for representative data.

## Pattern / Solution
1. Implement RUM using the Web Vitals library: onLCP, onINP, onCLS callbacks.\n2. Segment RUM data by device type, connection speed, geography, and page.\n3. Use p75 for thresholds (matching Google's approach); don't rely on averages.\n4. Build a dashboard combining RUM (real experience) and synthetic (regression detection).\n5. Investigate when RUM and synthetic diverge -- it usually reveals a real-world-only issue.

## Gotchas
- RUM requires real user traffic; low-traffic pages have insufficient samples for statistically significant data.\n- RUM data includes bots and crawlers; filter by User-Agent or interaction events.\n- Privacy regulations may limit RUM sampling; ensure consent compliance.

## Related
crux-field-data, lighthouse-scoring, performance-dashboard-design, load-testing-methodology
