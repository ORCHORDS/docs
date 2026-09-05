# SAML 2.0 SSO Integration Playbook

## Purpose

Stand up a new SAML 2.0 Service Provider (SP) integration against an Identity Provider (IdP) end-to-end: metadata exchange, AuthnRequest policy, assertion validation, single logout, and on-call runbook.

## Audience

Platform engineers, IAM operators, application owners.

## Pre-conditions

1. The IdP publishes current SAML 2.0 metadata.
2. The IdP signing cert rotation policy is documented.
3. The reference card for the protocol is current: `SAML_2_0_VERSION_GOVERNANCE.md`.
4. The SP supports signature and encryption per the policy table in the reference card.
5. The AuthnRequest, attribute, and NameID policies are agreed in writing with the IdP.

## Procedure

### 1. Metadata exchange

1. Generate SP metadata (entityID, ACS URL, SLO URL, signing/encryption certs).
2. Sign the SP metadata with the SP's signing cert.
3. Exchange metadata with the IdP (upload or pull from metadata URL).
4. Validate the IdP metadata (signature, expiration, contact).
5. Store the IdP metadata in a signed metadata cache with TTL ≤ 14 days.

### 2. AuthnRequest

1. Build the AuthnRequest XML with:
   - `ID` (unique), `Version="2.0"`, `IssueInstant` (current UTC time).
   - `Issuer` = SP entityID.
   - `AssertionConsumerServiceURL` = SP ACS URL.
   - `ProtocolBinding` = `urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST`.
   - `NameIDPolicy` = agreed format (default `urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress`).
   - `RequestedAuthnContext` per policy (default `PasswordProtectedTransport`).
   - `ForceAuthn` per policy.
2. Sign the AuthnRequest (or the surrounding `RelayState` form) with the SP signing key.
3. Encode and send via HTTP Redirect (deflated) or HTTP POST.
4. Set `RelayState` to the application URL the user should land on after auth.

### 3. Response (Assertion) handling

1. Receive the `SAMLResponse` via HTTP POST at the ACS URL.
2. Validate the `Issuer` against the cached IdP metadata.
3. Validate the `Destination` = ACS URL.
4. Validate the `InResponseTo` matches the original AuthnRequest `ID`.
5. Validate the `IssueInstant` is recent (within clock skew tolerance, ≤ 5 minutes).
6. Validate the assertion signature: algorithm per policy table; canonicalization per policy table.
7. Decrypt any encrypted assertion with the SP decryption key.
8. Validate the `SubjectConfirmation`:
   - `Method` = `urn:oasis:names:tc:SAML:2.0:cm:bearer`.
   - `Recipient` = ACS URL.
   - `NotOnOrAfter` is in the future.
   - `InResponseTo` matches the AuthnRequest `ID`.
9. Validate the assertion `Conditions`:
   - `NotBefore` is in the past.
   - `NotOnOrAfter` is in the future.
   - `AudienceRestriction` includes the SP entityID.
10. Validate the assertion `AuthnStatement`:
    - `AuthnInstant` is recent.
    - `SessionIndex` is recorded for SLO.
11. Validate attributes against the agreed attribute policy.
12. Map attributes to application claims.

### 4. Session and SLO

1. Maintain a session index mapping (session ID → SAML session index) for SLO.
2. SLO via HTTP Redirect or POST:
   - Send `LogoutRequest` to IdP SLO endpoint with the session index.
   - Receive `LogoutResponse` and validate.
3. Front-channel SLO: redirect the user to the IdP for global logout.
4. Back-channel SLO: SOAP-based logout to the IdP for service-initiated SLO.

### 5. Cert rotation

1. The IdP signing cert rotation policy is documented (typically 90 days).
2. On cert rotation: pull the new IdP metadata, validate the new signing cert, update the local trust store.
3. Maintain a list of active signing certs during a dual-cert transition window.
4. Per `SECRET_ROTATION_PLAYBOOK.md`.

### 6. Observability

- AuthnRequest count (counter).
- AuthnResponse received count (counter).
- Assertion validation failure rate (counter, by reason).
- SLO count (counter).
- Signature validation failure count (counter).
- Cert rotation event count (counter).

Audit log captures: `request_id`, `issuer`, `destination`, `subject`, `session_index`, `authn_instant`, `attributes`, `validation_result`.

### 7. Launch validation

1. Run integration test suite covering happy path, signature tampering, assertion expiry, audience mismatch, replay.
2. Confirm signature validation rejects unsigned assertions.
3. Confirm `InResponseTo` validation rejects replays.
4. Confirm SLO works.
5. Confirm cert rotation works.
6. Confirm attribute mapping is correct.

## Rollback

Rollback decisions:

- Assertion validation failure rate > 1% → investigate immediately.
- Signature validation failure → revert integration; coordinate with IdP.
- AuthnRequest rate > 10x baseline → likely misconfiguration; revert.

Rollback procedure:

1. Revert the integration to the last-known-good metadata.
2. Page the on-call IAM owner.
3. Trigger `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`.

## References

- `SAML_2_0_VERSION_GOVERNANCE.md`
- `SECRET_ROTATION_PLAYBOOK.md`
- `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`
- OASIS SAML 2.0 Core: `https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf`
- OASIS SAML 2.0 Profiles: `https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf`
