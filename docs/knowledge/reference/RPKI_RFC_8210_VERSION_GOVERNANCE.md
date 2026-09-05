---
title: RPKI Version Governance (RFC 6480, RFC 6482, RFC 8210, RFC 9319)
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: IETF RFC 6480 (February 2012); RFC 6481 (February 2012); RFC 6482 (February 2012); RFC 6483 (February 2012); RFC 6810 (January 2013); RFC 6811 (January 2013); RFC 7115 (January 2014); RFC 8210 (September 2017); RFC 8897 (September 2020); RFC 9319 (October 2022); https://www.rfc-editor.org/rfc/rfc6480
---

# RPKI Version Governance (RFC 6480, RFC 6482, RFC 8210, RFC 9319)

## Scope

This card governs how `orchords-docs` evaluates the Resource Public Key Infrastructure (RPKI) — the global, distributed PKI that supports BGP route origin validation and BGPsec path validation. RPKI is a binding input to the BGP reference architecture (`BGP_RFC_4271_VERSION_GOVERNANCE.md`) and to any Internet-routing reference card.

## Why this card exists

RPKI ties IP address resources (allocated by IANA and the RIRs) to public keys, and ties route origins to authorized ASNs. A KB card that recommends "BGP" without binding to RPKI Route Origin Authorizations (ROAs) and Route Origin Validation (ROV) produces an Internet-edge reference architecture that does not survive the current state of routing security expectations.

## Document set

- **RFC 6480** — An Infrastructure to Support Secure Internet Routing (February 2012).
- **RFC 6481** — A Profile for X.509 PKIX Resource Certificates (February 2012).
- **RFC 6482** — A Profile for Route Origin Authorizations (ROAs) (February 2012).
- **RFC 6483** — Validation of Route Origination Using the RPKI and Router Certificates (February 2012).
- **RFC 6810** — The RPKI to Router Protocol (RPKI-Router) — January 2013.
- **RFC 6811** — BGP Prefix Origin Validation (January 2013).
- **RFC 7115** — Origin Validation Operation Based on the RPKI (January 2014).
- **RFC 8210** — The RPKI to Router Protocol v2 (September 2017).
- **RFC 8897** — Requirements for the RPKI to Router Protocol (September 2020).
- **RFC 9319** — RPKI Manifests (October 2022).
- **RFC 9322** — RPKI Signed Object (September 2022).
- **RFC 9589** — On-Demand Validation of RPKI (July 2024) — drift detected at 2026-09.

References: `https://www.rfc-editor.org/rfc/rfc6480`, `https://www.rfc-editor.org/rfc/rfc8210`, `https://www.rfc-editor.org/rfc/rfc9319`.

## Hierarchy

RPKI follows the resource-allocation hierarchy:

```
IANA (root) → RIR (ARIN, RIPE, APNIC, LACNIC, AFRINIC) → NIR / LIR (optional) → ISP / End holder
```

Each level issues a Resource Certificate (X.509 PKIX profile per RFC 6481) to its subordinate.

## Object types

RPKI signs the following objects:

| Object | RFC | Purpose |
|---|---|---|
| Resource Certificate (RC) | RFC 6481, RFC 6487 | binds ASNs / IP blocks to public keys |
| Route Origin Authorization (ROA) | RFC 6482 | authorizes an AS to originate a prefix |
| Router Key (BGPsec router certificate) | RFC 8209 | authorizes a router to sign BGPsec updates |
| Manifest | RFC 9286 (replaces RFC 6486) | lists objects in the publication point |
| Ghostbuster Record | RFC 6493 | contact for the CA operator |
| Trust Anchor (TA) | RFC 8630 | the root of trust |

## Cryptographic algorithm policy

| Algorithm | Use case | Required? |
|---|---|---|
| RSA-2048 (RFC 4055) | RC, ROA | acceptable baseline |
| RSA-4096 | RC, ROA | preferred for new CAs |
| ECDSA P-256 | RC, ROA | recommended for new CAs |
| Ed25519 | RC, ROA | recommended for new CAs |
| SHA-256 | signature digest | mandatory |
| SHA-1 | signature digest | forbidden |

References: RFC 7935, RFC 8208 (RPKI elliptic curve profile), RFC 8211.

## Route Origin Validation (ROV)

ROV is the consumer-side validation:

- A relying party (RP) downloads the RPKI data (ROAs, manifests, certificates).
- The RP validates the signature chain to a configured trust anchor.
- For each BGP route, the RP determines the validation state:

| State | Definition | Action |
|---|---|---|
| Valid | at least one ROA covers the prefix and matches the originating ASN | accept |
| Invalid | at least one ROA covers the prefix and does NOT match the originating ASN | reject (configurable) |
| NotFound | no ROA covers the prefix | accept (default) or reject (configurable) |

References: RFC 6811, RFC 7115.

## RPKI to Router Protocol (RFC 8210)

RFC 8210 is the current version of the RPKI-Router protocol:

- Transports validated ROA payload (VRP) from the validator cache to the router.
- Uses Protocol Buffer over SSH or TCP/TLS.
- Default port: 323 (per IANA).

Versions: `protocol-version 0` (RFC 6810), `protocol-version 1` (RFC 8210), `protocol-version 2` (in development, drift detected at 2026-09).

## Required vs advisory

RPKI ROV is **advisory** today: per RFC 7115 § 3, the "NotFound" state may be treated as valid, invalid, or unknown. The KB reference card must declare the policy:

| Policy | Description |
|---|---|
| Permissive | NotFound = valid; Invalid = reject |
| Strict | NotFound = reject; Invalid = reject |
| Mixed | NotFound = accept for /24 and shorter; Invalid = reject |

## Mandatory pre-flight (before enabling ROV in production)

1. Validator cache is reachable (per `RPKI to Router` endpoint).
2. Trust anchors are configured (five RIR TAs minimum).
3. ROA coverage for the organization's prefixes is ≥ 99%.
4. Test invalid scenario: originate a prefix with mismatched ASN and confirm the BGP session drops the route.
5. Test unknown scenario: originate an unauthorized prefix and confirm the BGP session does NOT drop the route (default policy).

## Observability

- RPKI cache freshness (per RIR TA).
- Validated ROA count (gauge).
- RPKI validator query rate.
- BGP ROV state distribution: Valid, Invalid, NotFound (counters).
- RPKI to Router session health.

## Sources

- RFC 6480 (RPKI Architecture): `https://www.rfc-editor.org/rfc/rfc6480`
- RFC 6482 (ROA Profile): `https://www.rfc-editor.org/rfc/rfc6482`
- RFC 8210 (RPKI-Router v2): `https://www.rfc-editor.org/rfc/rfc8210`
- RFC 9319 (RPKI Manifests): `https://www.rfc-editor.org/rfc/rfc9319`
- MANRS: `https://www.manrs.org/`
- NLnet Labs Routinator / RPKI validator: `https://www.nlnetlabs.nl/projects/rpki/`
- FORT validator: `https://github.com/NICMx/FORT-validator`
