---
title: "SAML 2.0 Token Profile and Metadata Version Governance"
owner: "Knowledge Engineering"
status: "approved"
classification: "public"
last-reviewed: "2026-09-08"
review-cycle: "180 days"
next-review: "2027-03-07"
source: "OASIS SAML 2.0 Token Profile 1.0 (saml-profiles-2.0-os), SAML 2.0 Metadata (saml-metadata-2.0-os), and Kantara Initiative SAML 2.0 deployment profile guidance"
---

# SAML 2.0 Token Profile and Metadata Version Governance

This reference defines how the organisation governs SAML 2.0 token profiles, metadata descriptors, and supporting cryptographic choices across browser SSO and SOAP/WSS deployments. It is normative for version selection and interoperability testing.

## Scope and Profiles

SAML 2.0 token profiles apply to two transport contexts. Browser-based single sign-on uses the Web Browser SSO Profile over the HTTP Redirect and HTTP POST bindings. SOAP and WSS use the SAML 2.0 Token Profile 1.0 with WS-Security 1.2 or 1.3. The Enhanced Client or Proxy Profile (ECP) covers non-browser smart clients and is permitted only when documented in metadata.

## Assertions and NameID Formats

Approved NameID formats are `urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress` for opaque pairwise pseudonyms, X.500 for directory-aligned identifiers, `urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified` as a default, persistent identifiers for stable cross-session links, transient identifiers for privacy-preserving access, and encrypted forms where identifier confidentiality is required.

## Attribute Profiles

Attributes are published under the Basic Attribute Profile using the X.500, LDAP, and XSPA naming conventions. Mandatory attributes include `givenName`, `sn`, and `emailAddress`, each carrying NameFormat `urn:oasis:names:tc:SAML:2.0:attrname-format:uri` and a primitive `xs:string` type.

## Binding Selection and Metadata

Browser SSO uses HTTP Redirect for AuthnRequest delivery and HTTP POST for assertion response. Metadata documents MUST expose `EntityDescriptor`, `IDPSSODescriptor`, `SPSSODescriptor`, `KeyDescriptor` with `use="signing"` and `use="encryption"`, `SingleSignOnService`, and `SingleLogoutService`. `AttributeConsumingService` declares SP-driven attribute requirements and MUST be indexed.

## Cryptography

Signing uses XML Signature with RSA-SHA256 as default and ECDSA where mandated. Encryption follows SAML 2.0 XML Encryption with AES-GCM preferred and AES-CBC permitted, with key transport via RSA-OAEP.

## NameID Management and Single Logout

NameID Management governs account linking and identifier change. Single Logout variants include front-channel, back-channel, IdP-initiated, and SP-initiated; deployments MUST document the chosen variant in metadata.

## Deployment Profiles

Approved deployment profiles include eGovernment, eHealth, eIDAS, SIF (UK schools), Open Liberty, and ICAM. SOAP endpoints require compatibility with WS-Federation and WS-Security 1.2 or 1.3.

## Compatibility Horizon and Decision Tree

SAML 2.0 is the only supported version; SAML 2.1 is not expected. Selection follows a decision tree: browser SSO selects the Web Browser SSO Profile; SOAP selects the SAML Token Profile with WSS 1.2 or 1.3; signing selects RSA-SHA256 unless ECDSA is mandated; attributes follow the Basic Attribute Profile with `givenName`, `sn`, and `emailAddress`.

## Operational Impact

IdP rotation requires metadata refresh; SP signing key rollover is staged; metadata TTL is 14 days; expired metadata raises a configuration alarm.

## Cross-references

- [SAML 2.0 Version Governance](SAML_2_0_VERSION_GOVERNANCE.md)
- [Keycloak Version Governance](KEYCLOAK_VERSION_GOVERNANCE.md)
- [OAuth 2.1 Version Governance](OAUTH_2_1_VERSION_GOVERNANCE.md)

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
