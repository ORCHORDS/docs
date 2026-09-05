# OTP MFA Does Not Equal Phishing Resistance

**Issue:** A system is described as phishing-resistant because it uses a one-time password as a second factor.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

NIST SP 800-63B-4 distinguishes multi-factor authentication from phishing resistance. OTP and out-of-band authenticators that require a claimant to manually enter an authenticator output are not considered phishing-resistant because an impostor verifier can relay that output to the legitimate verifier.

## Engineering rule

- Do not label OTP-based MFA as phishing-resistant.
- Track MFA strength and phishing resistance as separate properties in authentication architecture and risk reviews.
- When phishing resistance is required, select a cryptographic authentication method that binds the authentication to the intended verifier or channel.
- Keep user education as a supplemental control rather than the mechanism that makes a protocol phishing-resistant.

## Verification

- Review each offered authenticator and classify whether it involves manual transfer of an authenticator output.
- Test whether a phishing proxy could relay the user-entered output to the real verifier.
- Confirm product and security documentation accurately distinguishes MFA from phishing resistance.

## Official source

- NIST SP 800-63B-4, Authenticators and Phishing Resistance: https://pages.nist.gov/800-63-4/sp800-63b/authenticators/
