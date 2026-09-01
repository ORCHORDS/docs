# NIST SP 800-63B Authentication and Lifecycle Version Governance

## Purpose

NIST SP 800-63B is the authenticator and authentication-lifecycle volume of the SP 800-63-3 Digital Identity Guidelines suite. It specifies the requirements for authenticators (memorized secrets, look-up secrets, out-of-band devices, single-factor and multi-factor cryptographic devices, software and hardware tokens) and the lifecycle requirements for binding authenticators to identities, refreshing them, and handling their loss, theft, or compromise.

A claim of "multi-factor authentication" should be cross-referenced with the SP 800-63B factor categories: something you know, something you have, or something you are. Authenticator Assurance Level AAL1, AAL2, and AAL3 are defined here, and the cryptographic requirements for each level are spelled out in this volume.

## Current context and source status

SP 800-63B was published in June 2017 alongside SP 800-63-3 and has received errata through March 2, 2020. The volume has been superseded together with the rest of the SP 800-63-3 suite by NIST SP 800-63-4 as of August 1, 2025. Implementations and documentation that continue to rely on SP 800-63-3 should record that fact and track their migration to SP 800-63-4.

## Governance pattern

1. Cite SP 800-63B explicitly when assigning or auditing AAL1, AAL2, or AAL3 to a verifier.
2. Classify each authenticator in use by the SP 800-63B categories and the permitted AALs for that category. For example, memorized secrets may be used at AAL1 and AAL2 (in combination with a second factor), but only multi-factor cryptographic devices meet AAL3.
3. Document the cryptographic requirements met by each authenticator type: FIPS 140 validation of the cryptographic module, secure display (where applicable), replay resistance, cloning resistance, and verifier-impersonation resistance.
4. Record authenticator lifecycle events: issuance, binding to a subscriber identity, re-binding, replacement, recovery, suspension, revocation, and destruction. Each event should be auditable.
5. Apply the rate-limiting and lockout guidance (for memorized secrets) and the secure-channel requirements (for out-of-band and cryptographic authenticators) defined in the volume.
6. Treat biometric authenticators as sensitive only when paired with a second factor at AAL2 or AAL3; a biometric alone is a "something you are" factor but is not, by itself, a multi-factor solution.
7. Where cryptographic operations are involved, ensure that the underlying module is validated to FIPS 140-2 or FIPS 140-3 as appropriate and that the security policy covers the algorithms in use.
8. Maintain a documented re-issuance and compromise-handling procedure for each authenticator type, including the verifier's role in re-binding or revocation.

## Authenticator assurance levels

AAL1 requires single-factor authentication with limited assurance. AAL2 requires two distinct authentication factors and approved cryptographic techniques. AAL3 requires a hardware-based authenticator with verifier-impersonation resistance and an additional identity-proofing verification. Implementations must demonstrate that each requirement of the claimed level is met, not that the level is "close to" met.

## Validation and evidence

Evidence includes:

- AAL assignment records with the authenticator type, factor count, and cryptographic mechanism;
- FIPS 140 security-policy references and certificate numbers;
- lifecycle event logs (issuance, binding, re-binding, replacement, revocation, destruction);
- documented rate-limiting, lockout, and session-handling rules;
- documented recovery procedures for lost, stolen, or compromised authenticators;
- test results showing that the AAL3 requirements (when claimed) are met, including verifier-impersonation resistance.

## Failure correction

Common defects include:

- AAL3 claimed because a hardware token is present, but the verifier-impersonation resistance requirement is not met because the verifier-side keys are not distinct from the authenticator-side keys.
- AAL2 claimed with two factors that share the same underlying secret (for example, a password plus an SMS code that is recoverable through the password-reset flow).
- Lifecycle events not recorded because the verifier platform treats authentication as a stateless function.
- Re-issuance performed without revoking the previous authenticator, leaving a window of dual-binding that defeats the lifecycle guarantee.

Corrective actions include re-baselining the AAL assignment, replacing or re-binding authenticators with proper revocation, and reissuing the verifier configuration with updated test evidence.

## Limitations

SP 800-63B does not specify:

- the cryptographic algorithms themselves (these are governed by FIPS 140-validated modules and SP 800-131A);
- the identity-proofing process (governed by SP 800-63-3 base and SP 800-63A);
- the federation assertion format (governed by SP 800-63C).

The publication also does not certify specific vendor products; it constrains their behavior when an AAL is claimed.

## Authenticator compromise handling

When an authenticator is lost, stolen, or otherwise compromised, the verifier-side response must include:

- immediate revocation of the compromised authenticator;
- re-issuance through the SP 800-63A identity-proofing lifecycle;
- audit-log entries that record the compromise, the response, and the re-issuance;
- notification to the subscriber and to any relying party that has accepted assertions from the compromised authenticator within the compromise window;
- a re-evaluation of the AAL assignment if the replacement authenticator is materially weaker.

Profiles that treat compromise as a recoverable error rather than a security event can leave relying parties exposed to replay or impersonation. SP 800-63B expects compromise handling to follow the same discipline as key compromise in SP 800-57 Part 1 Rev. 5.

## Reauthentication and session management

SP 800-63B requires reauthentication at AAL2 and AAL3 within a defined time period (12 hours at AAL2, 12 hours at AAL3 with additional restrictions) and limits the idle-session timeout (30 minutes at AAL2, 15 minutes at AAL3). Profiles should record these timeouts, the mechanism used to enforce them, and the test evidence that the timeouts cannot be extended by client-side manipulation.

For high-value transactions, SP 800-63B expects additional out-of-band confirmation or transaction-signing authenticators. Profiles that allow high-value transactions should document the transaction-signing path and bind it to the AAL, rather than relying on the session-time authentication alone.

## Federation and authentication

In federated architectures, the IdP is responsible for the AAL, and the relying party (RP) trusts the IdP's assertion per SP 800-63C. SP 800-63B does not specify federation details; profiles should cross-reference SP 800-63C and the assertion format profile used (for example, OpenID Connect with specific ACR/AMR values, or SAML with specific authnContextClassRef values). The RP should not assume that the IdP's AAL is sufficient without recording the assertion-format binding and the trust framework under which the IdP operates.

## Canonical sources

- NIST SP 800-63B, *Authentication and Lifecycle Management* (NIST pages): https://pages.nist.gov/800-63-3/sp800-63b.html
- NIST SP 800-63-3 base, *Digital Identity Guidelines* (NIST pages): https://pages.nist.gov/800-63-3/sp800-63-3.html
- NIST SP 800-63-4, *Digital Identity Guidelines* (NIST CSRC publication page): https://csrc.nist.gov/pubs/sp/800/63/4/final

Sources were verified on September 1, 2026.
