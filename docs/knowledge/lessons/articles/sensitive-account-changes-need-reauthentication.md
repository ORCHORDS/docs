# Sensitive Account Changes Need Reauthentication

**Issue:** Possession of an existing session or bearer token is enough to change the account email, password, MFA destination, or another takeover-sensitive attribute.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

OWASP API2:2023 identifies sensitive account changes without password confirmation or reauthentication as an authentication weakness. A stolen session should not automatically provide every credential-recovery or account-ownership capability.

## Engineering rule

- Identify account changes that materially affect authentication, recovery, or ownership.
- Require a fresh authentication step appropriate to the risk before completing those changes.
- Keep authentication secrets and tokens out of URLs.
- Validate token authenticity and expiry on every authentication boundary.
- Treat email, password, and MFA-factor changes as security events worth monitoring.

## Verification

- Attempt sensitive account changes using an old but otherwise valid session without fresh proof.
- Confirm the operation requires the intended reauthentication step.
- Verify tokens or passwords do not appear in request URLs, redirect locations, or other URL-carried parameters.

## Official source

- OWASP API2:2023 Broken Authentication: https://owasp.org/API-Security/editions/2023/en/0xa2-broken-authentication/
