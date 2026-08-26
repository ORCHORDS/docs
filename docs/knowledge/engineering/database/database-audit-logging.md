# database-audit-logging

**Issue:** No record of who accessed or modified sensitive data in the database
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Security incident requires knowing which rows were read by a compromised account. Compliance audit asks for data access logs.

## Pattern / Solution
Postgres options: log_statement = 'all' (logs all SQL), pgaudit extension (structured audit logs by object/role), trigger-based audit tables. For row-level audit trail: add modified_by column and trigger to populate from current_user. Ship logs to separate, append-only log store.

## Gotchas
- log_statement = 'all' can generate GBs of logs per hour -- use pgaudit for targeted logging
- Audit logs in the same database can be modified by admins -- ship to separate store
- Trigger-based audit tables double write I/O for audited tables

## Related
- data-retention-deletion
- database-encryption-at-rest
- row-level-security
