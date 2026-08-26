# multi-region-architecture

**Issue:** A single-region deployment has an unacceptable RPO/RTO for business requirements
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A regional cloud outage takes down all user-facing services for four hours, violating SLA commitments.

## Pattern / Solution
Deploy across multiple regions with traffic routing at the DNS or anycast layer. Choose between active-active (all regions serve traffic) and active-passive (standby warms up on failover). Data replication strategy dictates which is feasible.

## Gotchas
Multi-region adds significant complexity and cost. Data sovereignty laws may constrain which regions can hold which data. Cross-region replication lag can cause consistency issues in active-active configurations.

## Related
active-active-vs-active-passive, data-replication-strategies, disaster-recovery-architecture
