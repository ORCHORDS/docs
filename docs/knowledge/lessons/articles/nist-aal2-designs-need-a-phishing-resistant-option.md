# NIST AAL2 Designs Need a Phishing-Resistant Option

**Issue:** A system claims alignment with NIST AAL2 while offering only password-plus-OTP authentication paths.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

Under NIST SP 800-63B-4, a verifier operating at AAL2 SHALL offer at least one phishing-resistant authentication option. This is an assurance-level requirement in the NIST framework; it should not be generalized as a legal requirement for unrelated systems that do not claim or require NIST AAL2 alignment.

## Engineering rule

- When mapping a service to NIST AAL2, inventory the actual authenticator options users can choose.
- Ensure at least one deployed option satisfies NIST's phishing-resistance definition.
- Do not count SMS, email codes, TOTP, or other manually entered OTP outputs as the phishing-resistant option.
- Document which populations are required versus merely allowed to use the phishing-resistant path according to the applicable policy.

## Verification

- Trace a real AAL2 user from enrollment through authentication and identify the phishing-resistant option available to them.
- Confirm the option is deployed and usable, not only planned or documented.
- Verify the selected protocol meets the current NIST phishing-resistance criteria.

## Official source

- NIST SP 800-63B-4, Authenticator and Verifier Requirements: https://pages.nist.gov/800-63-4/sp800-63b.html
