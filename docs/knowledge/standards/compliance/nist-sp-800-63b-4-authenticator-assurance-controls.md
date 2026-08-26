# NIST SP 800-63B-4 Authenticator Assurance Controls

**Issue:** An authentication program that counts factors but ignores phishing resistance, verifier binding, recovery, and authenticator lifecycle can claim an assurance level it does not actually meet.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls
- Select the Authenticator Assurance Level from the service's risk analysis and document the permitted authenticator combinations for that level.
- Enforce verifier-name binding, replay resistance, protected channels, rate limiting, and approved secret handling appropriate to each authenticator type.
- Provide phishing-resistant options where required and do not describe an OTP or approval prompt as phishing-resistant when it can be relayed.
- Treat enrollment, binding, replacement, loss, revocation, recovery, and account notification as one controlled authenticator lifecycle.
- Apply the current memorized-secret rules, including blocklist screening and secure storage, without adding composition rules that undermine usability unless separately justified.
- Assess syncable authenticators and passkeys by their actual key protection, user verification, recovery, and deployment policy rather than by product name.

## Verification
- Trace each supported login and recovery path to the selected assurance-level requirements.
- Test phishing relay, replay, repeated guessing, lost-device recovery, authenticator replacement, and notification failure.
- Audit verifier storage, rate-limit behavior, and authenticator inventory after staff or device lifecycle events.

## Gotchas
Authentication assurance is determined by the weakest accepted path, including recovery and fallback, not by the strongest authenticator shown on the settings page.

## Official sources
- https://csrc.nist.gov/pubs/sp/800/63/b/4/final
- https://pages.nist.gov/800-63-4/
