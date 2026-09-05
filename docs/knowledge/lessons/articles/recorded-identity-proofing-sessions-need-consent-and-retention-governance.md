# Recorded Identity-Proofing Sessions Need Consent and Retention Governance

**Issue:** Video from an attended identity-proofing session is retained for fraud review without a documented privacy decision, applicant consent, or deletion schedule.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

NIST SP 800-63A-4 permits CSPs to record and maintain certain identity-proofing video sessions for fraud prevention and prosecution pursuant to a privacy risk assessment. If the CSP records the session, NIST requires advance notice, applicant consent before recording begins, and publication of the retention schedule and deletion process for those video records.

## Engineering rule

- Decide whether recording is needed through a documented privacy-risk assessment rather than making recording a default side effect.
- Notify the applicant before a recorded proofing session starts.
- Obtain consent before capture begins; do not treat consent after recording as equivalent.
- Define and publish the retention schedule and deletion process for proofing video.
- Restrict access to recorded sessions and preserve deletion evidence consistent with the organization's data-governance model.
- Keep fraud-investigation needs and privacy minimization in the same retention decision.

## Verification

- Attempt to start a recorded session without the required notice/consent and confirm recording cannot begin.
- Inspect retention configuration against the published schedule.
- Execute a safe deletion test and verify the record is removed from systems governed by the deletion process.
- Review access logs or equivalent evidence to confirm recorded sessions are restricted to approved roles.

## Official source

- NIST SP 800-63A-4, Identity Assurance Level Requirements — Remote and On-Site Attended Recording Requirements: https://pages.nist.gov/800-63-4/sp800-63a/ial/
