# Authentication Intent Needs an Explicit User Action

**Issue:** Possession of an active authenticator is treated as enough evidence that the user intentionally initiated the current authentication transaction.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

NIST SP 800-63B-4 separates possession of an authenticator from authentication intent. AAL2 SHOULD demonstrate authentication intent from at least one authenticator, while AAL3 authentication and reauthentication SHALL demonstrate it from at least one authenticator. The purpose is to show that the claimant knowingly participated in the specific authentication event rather than a credential operating silently without user awareness.

## Engineering rule

- When mapping authentication to NIST assurance levels, document how user intent is demonstrated.
- Prefer a deliberate user action tied to the current authentication transaction.
- Do not assume device possession, background key availability, or an existing session automatically demonstrates intent.
- Include reauthentication flows in the same intent review where the target assurance level requires it.

## Verification

- Walk through authentication with the user taking no deliberate action beyond having the authenticator present and determine whether authentication can complete.
- Confirm the AAL3 path requires an intent-demonstrating action for both initial authentication and reauthentication.
- Record the exact authenticator interaction used as intent evidence.

## Official source

- NIST SP 800-63B-4, Authenticator and Verifier Requirements: https://pages.nist.gov/800-63-4/sp800-63b.html
