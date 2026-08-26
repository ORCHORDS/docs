# data-retention-deletion

**Issue:** No automated data lifecycle leads to unbounded storage growth and compliance risk
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
GDPR right-to-erasure requests arriving with no deletion mechanism. Storage costs growing 20% month-over-month.

## Pattern / Solution
Define retention policy per data type in code. Implement as scheduled job with batched deletes. For GDPR erasure, implement user data deletion procedure covering all tables. Log all deletions to audit table.

## Gotchas
- Cascading FK deletes can be slow and lock many tables -- prefer explicit ordered deletion
- Soft-deleted rows need retention policy too
- Backups retain data beyond live deletion -- document backup retention separately

## Related
- archive-table-patterns
- soft-delete-schema-design
- database-audit-logging
