# log-retention-policies

**Issue:** Defining how long logs are kept in hot, warm, and cold storage tiers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Logs accumulate indefinitely and storage costs grow unbounded. Or logs are deleted too early and unavailable for security investigations.

## Pattern / Solution
Define three retention tiers: Hot (queryable, fast) — 7-30 days in Loki/Elasticsearch for operational troubleshooting. Warm (queryable, slow) — 90 days in S3/GCS with Athena or BigQuery for incident analysis. Cold (archived) — 1-7 years in Glacier/Coldline for compliance. Automate lifecycle policies via ILM, Loki compactor, or S3 Lifecycle rules. Review retention requirements with legal/compliance.

## Gotchas
Retention requirements vary by log type: security/audit logs typically require 1-7 years; application debug logs need only 7-30 days. GDPR requires deletion of PII within retention windows. Cost difference between S3 Standard and Glacier is 10x. Test restoration from cold storage annually.

## Related
log-sampling-strategies, log-security-masking, loki-retention-config
