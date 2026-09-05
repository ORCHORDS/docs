# Account Recovery Is an Authentication Surface

**Issue:** Login endpoints receive strict brute-force protection while forgot-password and recovery flows are treated as ordinary utility endpoints.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

OWASP API2:2023 explicitly states that forgot-password and reset-password flows should be treated as authentication mechanisms. A weaker recovery path can defeat a strong primary login flow.

## Engineering rule

- Inventory every way a user can authenticate or recover access, including web, mobile, deep-link, and recovery paths.
- Apply authentication-grade brute-force, rate-limiting, and lockout protections to credential recovery.
- Avoid revealing unnecessary account-existence information through recovery responses.
- Review recovery-token generation, validation, expiry, and one-time use according to the chosen authentication standards.
- Monitor recovery abuse separately from normal API traffic.

## Verification

- Compare login and recovery protections under repeated attempts against the same account.
- Test whether batching or alternate protocol features bypass the intended attempt limits.
- Confirm successful recovery invalidates or constrains the relevant recovery credential as designed.

## Official source

- OWASP API2:2023 Broken Authentication: https://owasp.org/API-Security/editions/2023/en/0xa2-broken-authentication/
