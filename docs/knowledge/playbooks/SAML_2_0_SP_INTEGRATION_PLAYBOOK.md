# SAML 2.0 Service Provider Integration Playbook

## Purpose

This playbook describes how to integrate a SAML 2.0 Service Provider (SP) with an enterprise Identity Provider (IdP). It covers metadata exchange, request and assertion signing, encryption of restricted attributes, attribute profile selection (Basic, X.500, XSPA), and Single Logout. Use it for first-time onboarding of a new application and as the canonical reference for recurring SP integrations.

## Audience

This playbook is intended for IAM engineers, application security engineers, integration engineers, and platform engineers who are responsible for deploying and operating SAML-based SSO between internal applications and the corporate IdP federation.

## Pre-conditions

Before starting the procedure, confirm all of the following:

- The enterprise IdP endpoint is reachable from the SP host on the required SAML ports and DNS resolves correctly.
- An SP metadata draft has been generated with at least EntityDescriptor, SPSSODescriptor, KeyDescriptor, AssertionConsumerService, and SingleLogoutService.
- X.509 signing and encryption certificates have been issued by the organization CA and are within their validity window.
- The attribute profile (Basic, X.500, or XSPA) has been agreed with the application owner and documented in the ticket.
- Discovery and metadata endpoint URLs are finalized and hosted on HTTPS with a trusted certificate.
- An audit log destination has been provisioned so that SAML requests, responses, and assertion validation results are recorded.

## Procedure

1. Generate the SP SAML 2.0 metadata document including EntityDescriptor, SPSSODescriptor, KeyDescriptor, AssertionConsumerService, and SingleLogoutService. Validate the XML against the OASIS SAML 2.0 schema before publication.
2. Publish the SP metadata to the IdP metadata federation and record the federation metadata URL for change-control tracking.
3. Configure the NameID Format. Use `urn:oasis:names:tc:SAML:2.0:nameid-format:persistent` for federation scenarios that require a stable subject identifier, and `urn:oasis:names:tc:SAML:2.0:nameid-format:transient` for privacy-preserving flows.
4. Configure signed AuthnRequests using the SP signing key, and require signed assertions from the IdP. Reject any assertion whose signature does not validate against the configured IdP certificate.
5. Configure encrypted assertions when transmitting restricted attributes. Use the SP encryption certificate and AES-256-GCM or AES-256-CBC as the data encryption algorithm.
6. Configure AttributeConsumingService with the agreed attribute set, including FriendlyName, Name, NameFormat, and isRequired flags per the chosen profile.
7. Configure Single Logout via front-channel HTTP-Redirect and ensure both the SP and IdP advertise matching SingleLogoutService bindings.
8. Wire IdP-initiated and SP-initiated flows. Disable IdP-initiated SSO unless the application explicitly requires it.
9. Set up just-in-time provisioning on first login, mapping SAML attributes to local user attributes according to the agreed profile.
10. Validate clock skew between the SP and IdP hosts within 3 minutes and enforce replay protection by checking the NotOnOrAfter condition on Conditions and SubjectConfirmationData.
11. Run a SAML-Tracer or browser DevTools capture for conformance, verifying RelayState, InResponseTo, Destination, and signature values.
12. Document the integration, store metadata and certificates in the team vault, and hand over to IAM ops with runbook links to this file and any IdP-specific cards.

## Rollback

If the integration must be reverted, unpublish the SP metadata from the IdP federation first so no further assertions are issued. Revoke the SP signing and encryption certificates through the organization CA. Disable the AssertionConsumerService endpoint at the load balancer and on the application host. Drain any in-flight assertions by rejecting requests whose InResponseTo does not match a stored request ID. Record the rollback in the change ticket and update the IAM operations runbook to reflect the disabled state.

## References

- See [SAML 2.0 Version Governance](../reference/SAML_2_0_VERSION_GOVERNANCE.md) for SAML governance policy and approved attribute profiles.
- See [SAML 2.0 Token Profile Version Governance](../reference/SAML_2_0_TOKEN_PROFILE_VERSION_GOVERNANCE.md) for token profile governance.
