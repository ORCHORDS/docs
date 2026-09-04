# NIST FAL3 Requires Subscriber Proof at the RP Beyond the Assertion

**Issue:** A federation transaction is labeled NIST FAL3 because the IdP assertion is strongly protected, but the RP never verifies an authenticator controlled by the subscriber.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

NIST SP 800-63C-4 makes FAL3 fundamentally different from bearer-assertion federation: the RP must verify that the subscriber controls an authenticator in addition to validating the assertion. The authenticator can be identified in a holder-of-key assertion or can be a bound authenticator maintained by the RP. For holder-of-key assertions, NIST requires the referenced authenticator to be phishing-resistant. A reference to a key is not enough if the subscriber never proves possession to the RP.

## Engineering rule

- Treat a bearer assertion by itself as insufficient for a NIST FAL3 session.
- After validating the assertion, require the subscriber to prove possession of the holder-of-key or bound authenticator directly to the RP.
- For holder-of-key assertions, require a phishing-resistant authenticator as specified by NIST.
- Ensure the authenticator identifier can be resolved to the correct RP subscriber account.
- If authenticator verification fails, do not create an authenticated FAL3 session even if the assertion itself is valid.

## Verification

- Present a valid FAL3-intended assertion without the associated authenticator proof and confirm the RP refuses to create the session.
- Present an incorrect or unbound authenticator and confirm the same refusal.
- For holder-of-key assertions, verify the referenced authenticator satisfies the current NIST phishing-resistance definition.
- Trace successful session creation and confirm both assertion validation and direct subscriber authenticator proof are evidenced.

## Official source

- NIST SP 800-63C-4, FAL3, Holder-of-Key Assertions, and Bound Authenticators: https://pages.nist.gov/800-63-4/sp800-63c.html
