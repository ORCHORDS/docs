# database-encryption-at-rest

**Issue:** Database files on disk are readable if storage media is compromised
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Compliance requirement (HIPAA, PCI-DSS) for encryption at rest. Concern about physical access to storage.

## Pattern / Solution
Options: OS/filesystem-level encryption (LUKS, dm-crypt -- transparent to Postgres), volume encryption (AWS EBS encryption -- easiest for cloud), application-level encryption (pgcrypto for specific sensitive columns). Key management via HSM or KMS (AWS KMS, HashiCorp Vault).

## Gotchas
- Filesystem encryption does not protect data in memory or in transit -- combine with TLS
- pgcrypto column encryption: encrypted data cannot be indexed efficiently -- store hashed version for lookup
- Performance impact of column-level encryption: 5-20% overhead for encrypted columns in hot path

## Related
- database-ssl-tls
- database-audit-logging
- column-level-security
