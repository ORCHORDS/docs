# W3C WebAuthn Level 3 Protocol Governance

## Purpose

W3C WebAuthn Level 3, "Web Authentication: An API for accessing Public Key Credentials," defines a web API for creating and using public key credentials. WebAuthn enables strong authentication using authenticators (platform authenticators like TPM, roaming authenticators like FIDO2 security keys) without transmitting a password or shared secret. This article governs the application of WebAuthn Level 3 so an organization can deploy strong authentication using the web platform's built-in capability.

## Scope

The specification applies to web applications and relying parties (RPs) that use WebAuthn. Within this knowledge base, the article covers the WebAuthn API (navigator.credentials.create, navigator.credentials.get), the registration and authentication ceremonies, the authenticator types, the attestation, the relying party identifier, and the documentation of the deployment. It does not cover the FIDO2 CTAP2 protocol (which authenticators use to communicate with the client); readers should consult the FIDO Alliance specifications for that.

## Workflow

1. Establish the WebAuthn policy: scope, relying party identifier, authenticator types supported, attestation policy, user verification policy, and the relationship to the broader authentication policy.
3. Implement the registration ceremony:
   - Generate a challenge on the server.
   - Pass the challenge to navigator.credentials.create with the public key credential creation options.
   - The authenticator creates a key pair and returns the public key, the credential ID, and the attestation.
   - Verify the attestation (where supported) and store the public key and the credential ID for the user.
4. Implement the authentication ceremony:
   - Generate a challenge on the server.
   - Pass the challenge to navigator.credentials.get with the public key credential request options.
   - The authenticator signs the challenge with the private key and returns the signed assertion.
   - Verify the signed assertion using the stored public key.
5. Manage the credential lifecycle: registration, authentication, renewal, and revocation.
6. Document the WebAuthn policy, the relying party identifier, the authenticator types, the attestation policy, and the lifecycle.

## Controls and evidence

WebAuthn controls include the documented policy, the challenge generation, the verification of attestation and assertions, the credential lifecycle, and the audit logs. Each WebAuthn operation should be traceable to the user, the authenticator, and the outcome.

## Validation

Validation should confirm the challenges are generated with sufficient entropy, the attestations are verified where supported, the assertions are verified using the stored public keys, the relying party identifier is consistent, and the credentials are managed for the user. Sample-based testing confirms the implementation.

## Failure correction

Common failure modes: challenges have insufficient entropy (correct: use a cryptographically secure random source with sufficient entropy); attestations are not verified (correct: verify the attestation using the expected attestation type); relying party identifier is incorrect (correct: use the correct RP ID matching the origin); credentials are not properly scoped (correct: scope the credentials to the user and the RP ID); revocation is not implemented (correct: implement revocation as part of the credential lifecycle).

## Limitations

WebAuthn Level 3 is a web API; it does not certify any relying party's deployment. The specification does not guarantee that all browsers support all features; readers should verify browser support. The specification depends on the authenticator's security; a compromised authenticator may compromise the credentials.

## Scope note

This article summarizes project-neutral reference use of W3C WebAuthn Level 3. It does not assert any specific relying party's conformance or claim any certification outcome.

## Canonical sources

- W3C Web Authentication: An API for accessing Public Key Credentials Level 3: https://www.w3.org/TR/webauthn-3/
- FIDO Alliance — FIDO2 Specifications: https://fidoalliance.org/specs/fido-v2.0-ps-20250214/fido-client-to-authenticator-protocol-v2.0-ps-20250214.html