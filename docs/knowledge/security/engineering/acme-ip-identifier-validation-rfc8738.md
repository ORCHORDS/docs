---
title: "Automated Certificate Management Environment (ACME) IP Identifier Validation Extension: Engineering and Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# ACME IP Identifier Validation

## Normative protocol requirements

IP orders use identifier type `ip`; the value is one IPv4 or IPv6 address, never a prefix or reverse-DNS name. The CA must offer `http-01` or `tls-alpn-01`; `dns-01` does not validate an IP identifier. HTTP validation contacts the address itself. Issued certificates encode SAN `iPAddress` as exactly 4 or 16 octets, not `dNSName`.

## Validation and interoperability

Submit IPv4 and IPv6 orders; serve the key authorization only at the ordered address. Test PTR substitution, redirects, wrong token/account thumbprint, timeout, and SAN tag/length. Log the destination contacted and resulting SAN bytes.

## Meaningful failure handling

Fail authorization for a non-IP identifier, invalid challenge response, or certificate without the exact iPAddress SAN encoding. Preserve the ACME problem type, destination, and SAN bytes; never substitute DNS-name validation or a textual SAN match.

## Canonical sources

- [RFC 8738](https://www.rfc-editor.org/rfc/rfc8738)
