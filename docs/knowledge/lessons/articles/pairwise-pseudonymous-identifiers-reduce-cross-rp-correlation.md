# Pairwise Pseudonymous Identifiers Reduce Cross-RP Correlation

**Issue:** The same stable subject identifier is sent to unrelated relying parties, making it easy for those RPs to correlate a subscriber even when they do not need a shared identity key.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

NIST SP 800-63C-4 defines pairwise pseudonymous identifiers (PPIs) as a way to give different RPs distinct federated identifiers for the same subscriber account. A PPI must contain no identifying information, must be difficult to guess with sufficient entropy, and normally must be disclosed to only one RP. A shared PPI is an explicit exception governed by the trust agreement, authorized-party notice and consent, an operational relationship among the RPs, RP consent, and a privacy risk assessment.

## Engineering rule

- Prefer a distinct PPI per RP when cross-RP correlation is unnecessary.
- Do not derive a PPI in a reversible or guessable way from email addresses, employee numbers, usernames, or other known subscriber data.
- Treat mappings between PPIs and upstream identifiers as subscriber information requiring protection.
- Use a shared PPI only when the trust agreement explicitly defines the RP set and the correlation need.
- Remember that a PPI alone cannot prevent correlation if the assertion also releases the same identifying attributes to multiple RPs.

## Verification

- Authenticate the same subscriber to two unrelated RPs and confirm the RPs receive different PPIs.
- Inspect generated PPIs for embedded or inferable identifying information.
- For any shared PPI, verify the trust agreement, authorized-party consent/notice, RP consent, operational justification, and privacy-risk assessment.
- Test that an RP outside the approved shared set cannot obtain the shared PPI.

## Official source

- NIST SP 800-63C-4, Pairwise Pseudonymous Identifiers: https://pages.nist.gov/800-63-4/sp800-63c.html
