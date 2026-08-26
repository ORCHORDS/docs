# PostgreSQL amcheck corruption detection and response

**Issue:** Latent heap or B-tree corruption may remain unnoticed until critical reads or maintenance touch damaged pages.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

PostgreSQL's `amcheck` extension provides verification functions for supported heap and B-tree structures. Run checks under a documented load and locking policy; a clean check is point-in-time evidence, not a substitute for checksums, backups, storage health, and recovery tests.

## Controls and verification

- Install through reviewed extension management.
- Start with lower-impact options and schedule deeper checks.
- Capture exact relation, function, options, server version, and error.
- Treat corruption evidence as an incident: preserve evidence and stop unsafe automated repair.
- Validate backups before remediation.
- Rehearse restore, reindex, and escalation decisions in non-production.

## Sources

- [PostgreSQL 18: amcheck](https://www.postgresql.org/docs/current/amcheck.html)
- [PostgreSQL 18: Data checksums](https://www.postgresql.org/docs/current/checksums.html)
