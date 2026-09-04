# Identity-Proofing Failure Redress Must Not Leak Mismatch Details

**Issue:** A failed identity-proofing flow tells the applicant exactly which identity attribute did not match, giving a fraudulent applicant feedback that can be used to improve the next attempt.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

NIST SP 800-63A-4 requires effective, secure, easy-to-find redress mechanisms for identity-proofing problems. At the same time, NIST advises that unsuccessful proofing should explain how to address the problem without revealing the specific mismatch that caused the failure, because such detail can teach fraudulent applicants which personal information is accurate.

## Engineering rule

- Give legitimate applicants clear recovery/redress instructions after proofing failure.
- Keep the public failure reason coarse enough that it does not disclose which field, evidence element, or authoritative-source comparison failed.
- Preserve detailed failure diagnostics in protected internal telemetry for authorized support and fraud investigation.
- Make alternative proofing methods clear when online proofing cannot be completed.
- Align support scripts, API errors, UI messages, and automated emails so one channel does not leak details another channel intentionally withholds.

## Verification

- Trigger failures for different mismatched attributes and confirm external responses do not reveal which field failed.
- Verify support and redress staff can access the evidence they need through controlled internal channels.
- Test that applicants can still discover an alternative proofing or redress path without receiving sensitive mismatch information.

## Official source

- NIST SP 800-63A-4, Privacy — Redress: https://pages.nist.gov/800-63-4/sp800-63a/privacy/
