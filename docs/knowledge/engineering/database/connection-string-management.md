# connection-string-management

**Issue:** Database credentials hardcoded in code or stored insecurely in environment files
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Connection string found in git history. Developer accidentally committed .env file. Production credentials same as development.

## Pattern / Solution
Store credentials in secrets manager (AWS Secrets Manager, HashiCorp Vault, Doppler). Inject at runtime via environment variables or secrets volume mount. Rotate credentials automatically without code deployment. Use IAM authentication for managed databases (RDS IAM auth) -- no password to rotate.

## Gotchas
- .env files must be in .gitignore from day one -- retroactive removal does not purge git history
- Secret rotation requires all connection pools to reconnect -- implement reconnect on auth failure
- Service accounts should have minimal privileges: SELECT only for read replicas, no DDL for application users

## Related
- database-ssl-tls
- database-encryption-at-rest
- connection-pooling-pgbouncer
