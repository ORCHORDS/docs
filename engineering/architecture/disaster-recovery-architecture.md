# disaster-recovery-architecture

**Issue:** Recovery from a major failure takes longer than the business can tolerate
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A database corruption event causes 12 hours of downtime because backups were never tested and the restore procedure was undocumented.

## Pattern / Solution
Define RPO (how much data loss is acceptable) and RTO (how long recovery takes). Match backup and replication strategy to these targets. Automate restore procedures. Test recovery quarterly with production-scale data. Document runbooks and keep them outside the primary system.

## Gotchas
Backups that are never restored are not verified. Backup storage in the same region as the primary is insufficient. Encryption of backups requires secure key management that survives the primary failure.

## Related
business-continuity-design, multi-region-architecture, active-active-vs-active-passive
