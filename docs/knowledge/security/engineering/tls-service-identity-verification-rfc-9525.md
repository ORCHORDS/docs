---
title: "TLS Service Identity Verification with RFC 9525"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# TLS Service Identity Verification with RFC 9525

## Purpose

RFC 9525 defines procedures for representing and verifying application-service identity in TLS. Certificate-path validation establishes that a certificate chains to an accepted trust anchor; service-identity verification separately establishes that the certificate identifies the service the client intended to reach. Both checks are required.

RFC 9525 obsoletes RFC 6125. New protocol profiles and implementations should cite the current specification while preserving protocol-specific rules where an applicable standard defines them.

## Identity contract

For every TLS client integration, record:

- the application protocol and its applicable identity specification;
- how the reference identifier is derived before connection establishment;
- which identifier types the protocol permits;
- the expected DNS name, IP address, or other protocol-defined identity;
- whether and how service discovery transforms the identifier;
- wildcard policy;
- trust-anchor and certificate-policy requirements; and
- the behavior on any mismatch or validation error.

The reference identifier must come from trusted configuration or authenticated discovery context. Do not replace it with an unauthenticated redirect target, a reverse-DNS result, or a name copied from the presented certificate.

## Verification sequence

1. Establish the intended service and reference identifier before processing the peer certificate.
2. Perform certificate-path validation, including validity, trust, key usage, and applicable revocation policy.
3. Compare the permitted reference identifier against the appropriate certificate identifier.
4. Apply protocol-specific matching and wildcard rules.
5. Reject the connection when identity verification fails.
6. Record a bounded diagnostic that does not expose certificate contents or sensitive endpoint details unnecessarily.

A successful TLS handshake is not proof that these application-layer identity checks occurred.

## Identifier handling

Use the subject alternative name extension and the identifier type defined for the protocol. Do not fall back to a certificate common name unless a governing protocol specification explicitly requires legacy behavior and that exception is documented.

Compare DNS names according to the specification rather than using general-purpose substring, suffix, locale-sensitive, or regular-expression matching. Treat IP-address identities as their defined binary address values, not as DNS names. Internationalized names require a documented conversion and comparison process consistent with the application protocol.

## Wildcards

Wildcard acceptance should be narrow and protocol-aware. Do not allow a wildcard to match multiple labels, partial labels, or an identity type for which wildcard matching is not defined. High-assurance services may prohibit wildcards entirely through policy.

## Discovery, aliases, and indirection

Service discovery can separate the user-facing name from the name used for routing. Follow the application protocol’s rules for deciding which identity is authenticated. A routing alias does not automatically become the authenticated service identity.

Preserve the original trusted identity through redirects and connection retries. If a protocol intentionally changes the authority, perform a new policy decision and identity verification rather than carrying forward the previous result.

## Failure behavior

Identity mismatch, missing required identifiers, invalid certificate paths, and unsupported name forms must fail closed. Do not add a user- or operator-controlled “continue anyway” path to unattended clients. Diagnostic overrides used in isolated testing must not be enabled in production configurations.

## Testing and evidence

Test exact matches, unrelated names, absent subject alternative names, expired and untrusted chains, wildcard boundaries, IP-address identifiers, discovery aliases, redirects, and internationalized names when supported. Verify that every failure prevents application data exchange.

Retain the identity contract, certificate-profile review, conformance tests, negative-test results, trust-store ownership, exception approvals, and migration records from RFC 6125-era behavior.

## Failure modes

Common failures include validating only the certificate chain, deriving the expected name from the certificate, accepting common-name fallback silently, using permissive wildcard matching, authenticating a routing alias without protocol authority, and logging complete certificates or internal endpoint inventories.

## Sources

- [RFC 9525: Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525)
- [RFC Editor information for RFC 9525](https://www.rfc-editor.org/info/rfc9525)
- [RFC 9325: Recommendations for Secure Use of TLS and DTLS](https://www.rfc-editor.org/rfc/rfc9325)
