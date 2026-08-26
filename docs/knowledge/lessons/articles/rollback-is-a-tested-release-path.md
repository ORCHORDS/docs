# Rollback is a tested release path

**Issue:** A rollback plan exists but fails because schema, state, credentials, flags, or artifacts are no longer backward compatible.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Version rollback artifacts and configuration; define state/data compatibility; use expand-contract migrations; preserve prior secrets only within safe rotation windows; specify trigger, authority, communications, and forward-fix boundary. Exercise rollback in production-like environments and after material release-pipeline changes.

## Verification

Deploy a canary, create representative state, roll back, verify data integrity and security controls, then roll forward. Measure recovery time and evidence artifact identity.

## Gotchas

Database rollback may be destructive. Old code can reject new tokens or data. “Redeploy previous commit” may rebuild different dependencies.

## Sources

- [NIST SP 800-218 SSDF](https://csrc.nist.gov/pubs/sp/800/218/final)
- [NIST CSF 2.0](https://www.nist.gov/publications/nist-cybersecurity-framework-csf-20)
