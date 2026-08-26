# secret-management-architecture

**Issue:** Credentials and API keys are stored in plaintext in configuration files and version control
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A developer accidentally commits a .env file containing database credentials. The credentials are now in git history.

## Pattern / Solution
Store secrets in a dedicated secrets manager such as Vault, AWS Secrets Manager, or GCP Secret Manager. Inject secrets at runtime via environment variables or mounted volumes. Rotate secrets automatically. Audit secret access. Never log secret values.

## Gotchas
Applications that cache secrets in memory must reload on rotation. Short secret lifetimes require reliable rotation automation. Access to secrets should be scoped by service identity, not shared team credentials.

## Related
configuration-management, api-security-architecture, zero-trust-architecture
