# Security finding suppression expiry and revalidation

**Issue:** A false-positive or accepted-risk suppression often outlives the code, detector, owner, and rationale that justified it, silently masking real regressions.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Lesson

Suppressions are temporary governed decisions, not deletion. Bind each suppression to the narrowest stable scope and force revalidation after expiry or material change.

## Required record

Capture tool/rule and version, finding fingerprint, exact resource/path, classification, evidence, threat reasoning, owner, independent approver, created/expiry dates, compensating control, and invalidation triggers.

## Controls

- Prefer correcting detector configuration or test fixtures over inline ignores.
- Scope by immutable finding identity where possible; never suppress an entire rule globally to silence one instance.
- Set shorter expiry for internet-exposed, authentication, cryptographic, and secret-related findings.
- Invalidate on code movement, dependency/tool upgrades, rule semantic changes, exposure changes, or owner departure.
- Keep suppressed findings visible in reports and metrics.
- Reopen automatically when evidence disappears or the fingerprint matches broader code.
- Require a fresh approval rather than automatic renewal.

## Verification

Inject a known-bad neighboring case and prove it remains detectable. Remove or alter the scoped line and ensure stale suppression fails. Review upcoming expirations and sample renewed decisions against current code.

## Gotchas

“Not exploitable” can change when architecture changes. File/line ignores are brittle. Scanner silence can mean ingestion failure. Never embed secrets or weaponized payloads in justification.

## Sources

- [NIST SP 800-218 SSDF](https://csrc.nist.gov/pubs/sp/800/218/final)
- [OpenSSF Scorecard check and remediation documentation](https://github.com/ossf/scorecard/blob/main/docs/checks.md)
