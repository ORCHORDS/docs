# database-ssl-tls

**Issue:** Database connections transmit credentials and data in plaintext without TLS
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Database accepting connections without SSL. Connection strings without sslmode=require.

## Pattern / Solution
Postgres: set ssl = on in postgresql.conf, provide server.crt and server.key. Client: connection string sslmode=require or sslmode=verify-full (with CA cert for mutual verification). Rotate certificates before expiry.

## Gotchas
- sslmode=require verifies encryption but not server identity -- use sslmode=verify-full to prevent MITM
- Certificate expiry causes connection failures -- monitor expiry and automate renewal
- Connection poolers (PgBouncer) need their own SSL config for each hop

## Related
- database-encryption-at-rest
- connection-pooling-pgbouncer
- row-level-security
