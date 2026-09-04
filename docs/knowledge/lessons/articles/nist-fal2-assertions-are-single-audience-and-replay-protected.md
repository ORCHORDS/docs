# NIST FAL2 Assertions Are Single-Audience and Replay-Protected

**Issue:** A NIST FAL2 deployment issues one assertion for several relying parties or accepts the same assertion more than once at an RP.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

NIST SP 800-63C-4 requires FAL2 assertions to be audience-restricted to a single RP and requires the RP to enforce replay protection. The final guidance also requires federated identifiers at FAL2 to avoid plaintext personal information such as usernames, email addresses, and employee numbers. Where the presentation includes an RP-request nonce, FAL2 and above require the RP to verify that nonce.

## Engineering rule

- Issue and validate FAL2 assertions for one RP audience only.
- Make replay protection an RP responsibility even when the IdP also limits assertion lifetime.
- Validate the RP audience, issuer, signature, time constraints, and protocol transaction binding before creating a session.
- Avoid plaintext PII in the federated identifier at FAL2.
- Verify protocol nonces or equivalent transaction-binding values required by the selected presentation mechanism.

## Verification

- Present an assertion issued for RP A to RP B and confirm RP B rejects it.
- Present the same FAL2 assertion twice to the intended RP and confirm the second use is rejected according to the federation protocol's replay model.
- Inspect federated identifiers for email addresses, usernames, employee numbers, or other plaintext personal information.
- Confirm the RP rejects responses with a missing or mismatched required transaction nonce.

## Official source

- NIST SP 800-63C-4, FAL2 and Assertion Presentation Requirements: https://pages.nist.gov/800-63-4/sp800-63c.html
