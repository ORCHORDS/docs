# NIST IAL2 Can Use a Non-Biometric Verification Pathway

**Issue:** A design assumes that NIST IAL2 always requires automated biometric comparison and therefore excludes applicants who cannot or do not use that verification method.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

NIST SP 800-63A-4 explicitly defines an IAL2 Non-Biometric Pathway. The pathway avoids automated comparison of biometric samples, although it can still involve manual visual comparison of an applicant to a portrait on identity evidence. NIST also permits approved non-biometric ownership-verification methods such as confirmation codes delivered to validated addresses, depending on the evidence class and proofing context.

## Engineering rule

- Do not equate IAL2 with mandatory automated biometric matching.
- Map the selected evidence classes to the non-biometric verification methods that NIST permits for those classes.
- Distinguish automated biometric comparison from manual visual comparison; the latter may still involve biometric data even though it is not an automated biometric pathway.
- If the service offers the Non-Biometric Pathway at IAL2, communicate its use to relying parties as required by NIST.
- Preserve evidence of which IAL2 pathway and verification method were used for the subscriber.

## Verification

- Walk through the non-biometric IAL2 path using representative evidence and confirm ownership verification follows an approved method for that evidence strength.
- Confirm the system records whether a mailed confirmation code or visual comparison was used where NIST requires that record.
- Verify relying-party documentation accurately communicates use of the Non-Biometric Pathway.
- Test that the pathway does not silently fall back to a weaker verification method than the selected IAL requires.

## Official source

- NIST SP 800-63A-4, Identity Assurance Level Requirements — IAL2 Non-Biometric Pathway: https://pages.nist.gov/800-63-4/sp800-63a/ial/
