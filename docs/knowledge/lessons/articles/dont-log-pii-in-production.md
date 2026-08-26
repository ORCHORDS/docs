# dont-log-pii-in-production

**Issue:** PII in log files turns a log aggregation breach into a data breach with regulatory consequences
**Date:** 2026-08-11
**Status:** documented

## What happened
An engineer added detailed request logging to debug an authentication issue. The logs included full request bodies, which contained email addresses, names, and in some cases partial payment details. The logs were shipped to a third-party log aggregator. That aggregator suffered a breach six months later. The company faced GDPR notification requirements for millions of users whose PII appeared in the logs.

## The lesson
Never log PII (names, emails, phone numbers, addresses, payment card data, government IDs, health data) in any log that is shipped to an external system or stored longer than necessary. Use opaque identifiers (user ID, order ID) in logs. Redact or mask sensitive fields before logging.

## Why it matters
Logs are often the least-secured store of data. They are shipped broadly, retained for years, and accessed by more people than the primary database. PII in logs multiplies the blast radius of any log-related breach and creates regulatory exposure.

## How to apply
- [ ] Define a list of PII field names (email, name, phone, address, ssn, card_number, etc.) and add them to a redaction blocklist.
- [ ] Implement logging middleware that redacts or hashes these fields before any log is written.
- [ ] Audit existing log samples for PII — grep for common patterns (`@`, `\d{4}-\d{4}-\d{4}-\d{4}`).
- [ ] Include a PII-in-logs check in code review guidelines.
- [ ] Set log retention policies to the minimum needed for operational debugging (e.g., 30 days, not forever).

## Related
- `audit-logs-are-append-only.md`
- `gdpr-by-design-not-retrofit.md`
- `data-minimization-reduces-breach-impact.md`
