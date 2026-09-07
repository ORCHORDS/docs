# OIDC FAPI 2.0 Integration Playbook

## Purpose
Deliver a FAPI 2.0-conformant open-API deployment using OIDC Core and OAuth 2.1 with DPoP or mTLS sender-constrained tokens. This playbook codifies the configuration, evidence collection, and certification activities required to move an open-banking or regulated API platform from a FAPI 1.0 baseline to a FAPI 2.0 Security Profile production state. Treat each step as a gating control: skip none. Engineers should retain configuration diffs and tool output for the certification audit package. Update the platform risk register once production flag flip is complete.

## Audience
- API platform engineers
- Security engineers
- Compliance officers
- Open-banking governance leads

## Pre-conditions
Confirm the following before starting the procedure:
- Signed certificates issued by the organization CA, with the issuer chain trusted by the authorization server.
- PAR-capable authorization server (RFC 9126), with the pushed authorization request endpoint publicly reachable.
- JARM-capable authorization server (RFC 9901), with signing and encryption keys registered.
- mTLS endpoint or DPoP-capable application server for sender-constrained token issuance.
- Conformance test suite access, including the OpenID Foundation FAPI test runner.
- OpenID Foundation FAPI certification lab registration, with a target certification window booked.

## Procedure
Execute the following steps in order. Capture evidence at each step, including server logs, request captures, and configuration exports.

1. Issue an organization-issued sender certificate for the TPP. Record SAN entries, key type, and validity period.
2. Configure the authorization server with FAPI 2.0 Security Profile metadata, advertising the supported profiles in the discovery document.
3. Enable mandatory PKCE (RFC 7636) for the authorization code flow. Reject requests without S256.
4. Enable the PAR (RFC 9126) endpoint and require its use for all confidential clients. Reject non-PAR authorization requests.
5. Configure JARM (RFC 9901) for JWT-secured authorization responses, including signing and encryption keys.
6. Configure DPoP (RFC 9449) or mTLS (RFC 8705) proof on the token endpoint. Reject tokens bound to neither mechanism.
7. Issue sender-constrained access tokens with the cnf claim (RFC 7800), binding the token to the DPoP key or mTLS certificate.
8. Enforce strict RFC 9700 redirect URI matching server-side, including exact string comparison.
9. Configure resource indicators (RFC 8707) for audience binding on the token request.
10. Validate JSON Web Signature on all request objects, including issuer, audience, and expiration claims.
11. Run a pre-conformance self-test using the OpenID Foundation toolset. Capture logs and pass/fail evidence.
12. Schedule the formal conformance certification with the FAPI certification lab.
13. Document evidence and promote to production behind a feature flag for progressive rollout.

## Rollback
If production health or compliance is at risk, execute the following:
- Revoke issued certificates through the CA.
- Rotate signing keys on the authorization server and resource server.
- Disable client registration for the FAPI 2.0 profile.
- Revert to the FAPI 1.0 baseline if the FAPI 2.0 profile cannot be stabilized.
- Document the rollback in the change log and notify governance.
- Confirm certificates are revoked across all resource server trust stores before resuming baseline traffic.

## References
- [OIDC FAPI 2.0 Version Governance](../reference/OIDC_FAPI_2_VERSION_GOVERNANCE.md)
- [OAuth 2.1 Version Governance](../reference/OAUTH_2_1_VERSION_GOVERNANCE.md)
- [Keycloak Version Governance](../reference/KEYCLOAK_VERSION_GOVERNANCE.md)
- OpenID Foundation FAPI: https://openid.net/fapi/
- OpenID Foundation FAPI 2.0 Security Profile specification
- RFC 7636 (PKCE), RFC 9126 (PAR), RFC 8705 (mTLS), RFC 8707 (Resource Indicators), RFC 9449 (DPoP), RFC 9700 (OAuth 2.0 BCP), RFC 7800 (cnf claim), RFC 9901 (JARM)