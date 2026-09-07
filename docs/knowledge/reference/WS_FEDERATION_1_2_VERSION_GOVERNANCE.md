---
title: "WS-Federation 1.2 and WS-Security 1.2 Version Governance"
owner: "Knowledge Engineering"
status: "approved"
classification: "public"
last-reviewed: "2026-09-08"
review-cycle: "180 days"
next-review: "2027-03-07"
source: "OASIS Web Services Federation (WS-Federation) 1.2, WS-Security 1.2 (wss-v1.2), WS-Trust 1.4, and OASIS Public Profile 1.1 guidance"
---

# WS-Federation 1.2 and WS-Security 1.2 Version Governance

## Overview

WS-Federation 1.2 defines a federated identity model built on WS-Security, WS-Trust, and WS-Policy. It is the foundation used by Microsoft's Active Directory Federation Services (ADFS), Windows Identity Foundation (WIF), and Microsoft Entra (formerly Azure Active Directory) when interoperating with SOAP- or HTTP-Redirect-based relying parties. The federation language operates with Security Token Services (STS) that issue SAML 1.1, SAML 2.0, or JWT tokens, and supports both passive requestors (browsers) and active requestors (SOAP clients).

## WS-Security 1.2 SOAP message security

WS-Security 1.2 (wss-v1.2) specifies how security tokens are bound to SOAP messages. The supported token types include UsernameToken (with optional password digest), X.509Token, SAMLToken (1.1 and 2.0), and KerberosToken. Token reference and signature use XML Signature; confidentiality uses XML Encryption. The specification is current; the OASIS technical committee published errata and clarifications through 2024, and the latest interop profiles are catalogued in the OASIS Public Profile 1.1.

## WS-Trust 1.4 token issuance

WS-Trust 1.4 defines the STS contract: Issue, Renew, Cancel, Validate, and Key Exchange Token (KET). The RST/RSTR message exchange carries the request, the issued token, and any negotiated proof-of-possession keys. WS-Trust underpins federation flows where a relying party needs a SAML or JWT bearer token to call a downstream service.

## Federation metadata and realm

WS-Federation metadata is published as an XML document containing the realm identifier, federation endpoint URLs, supported token types, and signing certificates. The realm is the unique key for federation routing and is the string the IdP uses to dispatch incoming passive requests to the correct relying party.

## Passive and active requestor flows

Passive requestor flows target browsers via HTTP GET/POST through the sign-in and sign-out endpoints; Identity2009 and SAML2 token formats are typical. Active requestor flows target SOAP clients that submit a RequestSecurityToken (RST) directly to the STS endpoint and receive a RequestSecurityTokenResponse (RSTR).

## Compatibility horizon

WS-Federation 1.2 is the final mainstream specification; no 1.3 version is planned. ADFS in Windows Server 2022 supports WS-Federation 1.2 alongside SAML 2.0 and OpenID Connect. Microsoft Entra continues to accept WS-Federation sign-in for legacy tenants. New deployments SHOULD prefer OIDC or SAML 2.0; WS-Federation is acceptable only when an existing application mandates it.

## Version selection decision tree

Choose passive requestor when the relying party is a browser application; choose active requestor when the relying party is a SOAP client. Choose SAML 2.0 as the token format when downstream services already speak SAML; choose JWT when downstream services are HTTP/REST-based. Configure realm rotation through a documented metadata refresh interval; align certificate validity with the corporate PKI policy.

## Operational impact points

Certificate rotation on the STS signing key triggers a federation metadata republish. Clock skew between relying party and STS must remain within 5 minutes. Token replay is mitigated through the `<wsu:Timestamp>` Nonce and Created/Expires attributes. Federation metadata endpoints must be reachable on port 443 with mutual TLS where mandated by the integration profile.

## Cross-references

See [SAML 2.0 Token Profile Version Governance](SAML_2_0_TOKEN_PROFILE_VERSION_GOVERNANCE.md), [Keycloak Version Governance](KEYCLOAK_VERSION_GOVERNANCE.md), and [OAuth 2.1 Version Governance](OAUTH_2_1_VERSION_GOVERNANCE.md) for protocol governance of adjacent federation patterns.

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
