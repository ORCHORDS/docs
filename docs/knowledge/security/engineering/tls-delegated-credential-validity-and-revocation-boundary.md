# TLS delegated-credential validity and revocation boundary

**Issue:** A TLS delegated credential is operated like an ordinary certificate with online early revocation, so compromise response and session resumption can leave the credential usable until an incorrectly enforced expiry.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Boundary

RFC 9345 lets a certificate owner delegate TLS or DTLS 1.3 authentication to a short-lived key without placing the certificate private key at the edge. The delegated credential is bound to the end-entity certificate. Unless an application profile defines another maximum, its validity is limited to seven days and cannot extend beyond the delegation certificate.

## Controls

- Keep the end-entity certificate private key in the controlled credential-issuing tier; generate delegated private keys at the narrowest practical edge boundary.
- Require the certificate's DelegationUsage extension and the key usages and signature schemes permitted by the RFC and local policy.
- Issue credentials substantially shorter than the seven-day protocol maximum and rotate before expiry with bounded overlap.
- Compute and validate expiry from the certificate `notBefore` plus delegated `valid_time`; also enforce current time, remaining maximum validity, and certificate expiry.
- Use a monitored, authenticated time source and define clock-skew failure behavior.
- Distribute keys and credentials atomically, remove superseded private keys, and inventory every active credential by site.
- On compromise, stop issuance, remove the key from all endpoints, rotate immediately, and revoke the parent certificate when exposure or containment requires it.
- Revalidate the associated delegated credential when resuming sessions if the certificate chain is cached and revalidated.

## Verification

Test valid, expired, future-skewed, over-seven-day, beyond-certificate-expiry, wrong-certificate, unsupported-scheme, missing-DelegationUsage, TLS 1.2, and tampered credentials. Exercise rotation and compromise while traffic is active and confirm old keys disappear from every edge before the incident is closed.

## Gotchas

Delegated credentials have no additional early-revocation mechanism: expiry is their normal revocation, while revoking the signing certificate implicitly revokes them. Short lifetime reduces but does not eliminate compromise exposure. Client support and fallback behavior must be measured before rollout.

## Official sources

- [RFC 9345: Delegated Credentials for TLS and DTLS](https://www.rfc-editor.org/rfc/rfc9345.html)
