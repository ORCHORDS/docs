---
title: SAML 2.0 Version Governance (OASIS Security Assertion Markup Language)
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: OASIS SAML 2.0 (March 2005) — Assertions and Protocols (saml-core-2.0-os), Bindings (saml-bindings-2.0-os), Profiles (saml-profiles-2.0-os), Metadata (saml-metadata-2.0-os); https://docs.oasis-open.org/security/saml/v2.0/
---

# SAML 2.0 Version Governance (OASIS Security Assertion Markup Language)

## Scope

This card governs how `orchords-docs` evaluates SAML 2.0 as an identity federation protocol. It is the reference input for any SSO integration card that targets a SAML 2.0 identity provider (IdP) — Okta, Microsoft Entra ID, Google Workspace, PingFederate, Shibboleth.

## Why this card exists

SAML 2.0 is stable since 2005; the operational pain comes from inter-vendor profile variations (AuthnRequest scoping, Signature Wrapping, ECP profile support, encrypted assertion policy). A KB card that recommends "SAML SSO" without pinning the binding and signature/encryption policy produces an integration that breaks the moment the IdP rotates its signing cert.

## Document set

SAML 2.0 is a stack of four OASIS documents:

- **saml-core-2.0-os** — Assertions and Protocols (request/response, statements, attribute profiles).
- **saml-bindings-2.0-os** — How SAML messages are transported (HTTP Redirect, HTTP POST, HTTP Artifact, SOAP, Reverse SOAP).
- **saml-profiles-2.0-os** — Use cases (Web Browser SSO, Single Logout, ECP, Artifact Resolution).
- **saml-metadata-2.0-os** — How IdPs and SPs advertise capabilities.

References: `https://docs.oasis-open.org/security/saml/v2.0/`.

## Profile support matrix

| Profile | Status | Notes |
|---|---|---|
| Web Browser SSO Profile (HTTP Redirect + POST binding) | required baseline | every SAML integration supports this |
| Single Logout (SLO) Profile | required | HTTP Redirect + POST binding |
| Enhanced Client or Proxy (ECP) Profile | optional | used by smart-card / federated desktops |
| Assertion Query/Request Profile | optional | rarely used |
| Artifact Resolution Profile | required when SAML artifact binding is used | uncommon |
| Name Identifier Management Profile | optional | account linking migration |

## Binding support matrix

| Binding | Use case | Required |
|---|---|---|
| HTTP Redirect (GET) | AuthnRequest, LogoutRequest | yes |
| HTTP POST | AuthnRequest, Response, LogoutRequest, LogoutResponse | yes |
| HTTP Artifact | high-security federation | optional |
| SOAP | ECP, Artifact Resolution | optional |
| Reverse SOAP | deprecated | n/a |

References: `https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.html`.

## Signature and encryption policy

The project enforces:

- **Signing algorithm**: `rsa-sha256` (RSA-SHA256) or `ecdsa-sha256` (ECDSA-SHA256 with NIST P-256). `rsa-sha1` is forbidden.
- **Digest algorithm**: `sha-256`. `sha-1` is forbidden.
- **Canonicalization**: `exc-c14n` (Exclusive XML Canonicalization 1.0). `none` and `c14n` are forbidden.
- **Encryption**: `aes128-cbc` or `aes256-cbc` or `aes128-gcm`. AES-CBC alone is acceptable; prefer AES-GCM. 3DES is forbidden.
- **Key transport**: `rsa-oaep-mgf1p` (RSA-OAEP with MGF1 padding).
- **Reference**: SAML 2.0 XML Security specifications (March 2005 errata).

## Name ID and attribute policy

| Field | Policy |
|---|---|
| NameID Format | `urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress` (default) or `urn:oasis:names:tc:SAML:2.0:nameid-format:persistent` |
| Attribute `email` | always required |
| Attribute `given_name` | required for human-facing flows |
| Attribute `family_name` | required for human-facing flows |
| Attribute `groups` | required for RBAC flows; values are CN/DN of the groups |
| Attribute `eduPersonAffiliation` | optional, used in academic federations |

## AuthnRequest policy

The project's AuthnRequest template enforces:

- `ForceAuthn = true` for high-assurance flows (admin SSO, financial transactions)
- `IsPassive = false` for most flows
- `ProtocolBinding = urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST`
- `AssertionConsumerServiceURL` pinned to the SP's ACS endpoint
- `RequestedAuthnContext` policy:
  - `urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport` (default)
  - `urn:oasis:names:tc:SAML:2.0:ac:classes:X509` (smart card)
  - `urn:oasis:names:tc:SAML:2.0:ac:classes:Kerberos`

## Single Logout policy

- LogoutRequest is sent to the IdP via HTTP Redirect or HTTP POST.
- The IdP responds with LogoutResponse. Status code `urn:oasis:names:tc:SAML:2.0:status:Success` indicates clean logout.
- Front-channel logout (Redirect/POST) is the default. Back-channel logout (SOAP) is supported but discouraged.
- LogoutRequest signature is mandatory; the project refuses unsigned LogoutRequest.

## Metadata policy

The project publishes and consumes SAML 2.0 Metadata (saml-metadata-2.0-os). The metadata document must include:

- EntityDescriptor with the entityID.
- IDPSSODescriptor or SPSSODescriptor as appropriate.
- KeyDescriptor with the signing key.
- SingleSignOnService / AssertionConsumerService for each binding used.
- SingleLogoutService for each binding used.
- ValidUntil timestamp (max 14 days after publication).
- ContactPerson of type `technical` and `support`.

The project enforces metadata freshness: metadata older than 14 days is rejected.

## Mandatory pre-flight (before adopting a new SAML IdP integration)

1. IdP publishes current SAML 2.0 metadata.
2. IdP signing cert rotation policy documented.
3. IdP supports Signature Wrapping defenses (per MITRE 2018 paper on signature wrapping attacks).
4. AuthnRequest policy is agreed in writing.
5. Attribute policy is agreed in writing.
6. NameID format is agreed.
7. ACS URL and SLO URL are pinned and on the allowlist.

## Sources

- SAML 2.0 Core: `https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf`
- SAML 2.0 Bindings: `https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf`
- SAML 2.0 Profiles: `https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf`
- SAML 2.0 Metadata: `https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf`
- SAML 2.0 XML Security (Errata): `https://www.oasis-open.org/committees/security/`
- NIST SP 800-63-4 (Digital Identity Guidelines): `https://pages.nist.gov/800-63-4/`
