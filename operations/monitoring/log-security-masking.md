# log-security-masking

**Issue:** Redacting sensitive data from logs before storage and transmission
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Logs contain credit card numbers, passwords, tokens, or PII. A log system breach exposes sensitive user data.

## Pattern / Solution
Implement log masking at emission: use a structured logging wrapper that redacts fields named password, token, card_number, ssn. Apply regex-based scrubbing for patterns like card numbers and SSNs. For unstructured systems use a log pipeline filter (Vector transforms, Fluentd) to mask before ingestion. Run a log audit job quarterly that scans for PII patterns. Never log raw request bodies containing payment data.

## Gotchas
Masking at source is safer than masking in pipeline. Mask patterns need to handle partial matches. API keys logged in HTTP headers are a common miss — mask Authorization and X-API-Key headers. Log masking can be bypassed by debug logs — enforce via linter rules.

## Related
log-structured-logging, log-retention-policies, log-correlation-ids
