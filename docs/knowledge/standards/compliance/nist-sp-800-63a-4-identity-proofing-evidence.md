# NIST SP 800-63A-4 Identity-Proofing Evidence

**Issue:** Collecting identity documents without a declared assurance target, evidence-quality decision, fraud controls, or redress process produces more sensitive data without dependable identity proofing.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls
- Select and document the required Identity Assurance Level from risk and impact analysis before choosing collection methods.
- Resolve the claimed identity, validate the authenticity and validity of presented evidence, and verify that the applicant is the person associated with that evidence.
- Use evidence and verification methods that meet the selected assurance level; record permitted exceptions and compensating controls.
- Apply fraud detection, duplicate-enrollment checks, protected notification, and escalation for suspected synthetic or stolen identities.
- Collect and retain only attributes and evidence needed for the proofing purpose. Publish retention, deletion, privacy, and subscriber-notice rules.
- Provide accessible exception handling and redress without weakening the normal proofing decision or silently lowering assurance.

## Verification
- Map every enrollment step and stored artifact to the selected assurance requirement and an accountable owner.
- Test forged, expired, mismatched, replayed, and duplicate evidence plus supervised exception cases.
- Sample completed enrollments for proofing records, applicant notification, retention expiry, and redress traceability.

## Gotchas
Identity proofing establishes confidence in a claimed real-world identity. It does not replace authenticator strength, federation controls, or ongoing account-risk monitoring.

## Official sources
- https://csrc.nist.gov/pubs/sp/800/63/a/4/final
- https://pages.nist.gov/800-63-4/
