# Dependency risk exception renewal

**Issue:** A vulnerable or unmaintained dependency exception becomes permanent because its original owner, alternatives, and exposure are never reconsidered.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Record exact package/digest, affected products, vulnerability/license/maintenance risk, reachability, compensating control, owner, approver, expiry, replacement plan, and evidence. Revalidate on new advisory, KEV entry, exploit signal, release, ownership change, or architecture change. Renew through fresh approval; never auto-extend.

## Verification

Test the compensating control, inventory all deployed copies, confirm upgrade/replacement feasibility, and fail CI/policy after expiry. Sample exceptions for stale owners and unsupported versions.

## Gotchas

A lockfile preserves the risky version. “No fix available” changes over time. Suppressing scanner output is not risk acceptance.

## Sources

- [NIST SSDF project](https://csrc.nist.gov/projects/ssdf)
- [CISA Known Exploited Vulnerabilities Catalog](https://www.cisa.gov/known-exploited-vulnerabilities-catalog)
