---
title: BGPsec Version Governance (RFC 8205, RFC 8209, RFC 8211)
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: IETF RFC 8205 (September 2017); RFC 8209 (September 2017); RFC 8211 (September 2017); RFC 8208 (September 2017); https://www.rfc-editor.org/rfc/rfc8205
---

# BGPsec Version Governance (RFC 8205, RFC 8209, RFC 8211)

## Scope

This card governs how `orchords-docs` evaluates BGPsec — the cryptographic path-validation extension to BGP-4 that ties AS-Path to authorized route origins via RPKI certificates. BGPsec is a binding input to the BGP reference architecture (`BGP_RFC_4271_VERSION_GOVERNANCE.md`) and to the RPKI reference architecture (`RPKI_RFC_8210_VERSION_GOVERNANCE.md`).

## Why this card exists

BGPsec extends BGP-4 to provide route-origin authentication, AS-Path authentication, and AS-Path sequence assurance via signatures carried in a BGPsec UPDATE message. A KB card that cites BGPsec without binding to the supporting RPKI router keys (RFC 8211) and protocol extensions (RFC 8209) produces a reference architecture that cannot reason about its own cryptographic state.

## Document set

- **RFC 8205** — BGPsec Protocol Specification (September 2017).
- **RFC 8209** — BGPsec Operational Considerations (September 2017).
- **RFC 8211** — BGPsec Router Key Rollover (September 2017).
- **RFC 8208** — BGPsec Algorithms, Key Formats, and Signature Formats (September 2017).

References: `https://www.rfc-editor.org/rfc/rfc8205`, `https://www.rfc-editor.org/rfc/rfc8209`.

## Protocol version support matrix

| Spec | Status | Notes |
|---|---|---|
| RFC 8205 (BGPsec protocol) | IETF Standard (September 2017) | mandatory baseline |
| RFC 8209 (operational considerations) | IETF Standard (September 2017) | operating practices |
| RFC 8211 (router key rollover) | IETF Standard (September 2017) | key lifecycle |
| RFC 8208 (algorithms, key formats) | IETF Standard (September 2017) | algorithm policy |

## BGPsec UPDATE message

BGPsec extends the BGP UPDATE message with:

- **BGPsec_PATH** attribute — replaces (or augments) the BGP AS_PATH.
- **Signature** list — one signature per AS hop.
- **Secure_Path** — contains flags for each hop (valley-free enforcement).
- **Signer** — the router that produced the signature.

## Algorithm policy

| Algorithm | Use case | Required |
|---|---|---|
| ECDSA P-256 (RFC 5480) | BGPsec signatures | preferred |
| Ed25519 (RFC 8032) | BGPsec signatures | preferred for new deployments |
| RSA-2048 / SHA-256 | legacy support | deprecated |
| RSA-4096 / SHA-256 | legacy support | allowed |

References: RFC 8208 § 2.

## Router key lifecycle (RFC 8211)

BGPsec routers hold RPKI-issued router certificates. The lifecycle:

1. **Key generation** — router generates an ECDSA P-256 or Ed25519 keypair.
2. **Certificate request** — the operator requests a router certificate from the CA.
3. **Certificate installation** — the operator installs the certificate on the router.
4. **Active period** — the router signs updates with the active key.
5. **Rollover** — a new key/cert is installed alongside the old; both are active for the rollover window (≥ 24 hours).
6. **Retirement** — the old key is decommissioned; the cert is revoked at the CA.

The rollover procedure per RFC 8211:

- **Pre-rollover**: new key/cert is generated and installed alongside the active.
- **Roll-over**: router switches to the new key for signing.
- **Post-rollover**: the old key/cert is retained for the validation window (≥ 8 hours).
- **Decommission**: the old key/cert is removed and revoked.

## Valley-free routing enforcement

BGPsec enforces valley-free AS-Path validation: the sequence of AS hops must not violate the valley-free property (provider-customer and peer-peer edges must not be re-traversed).

## Mandatory pre-flight (before enabling BGPsec)

1. RPKI router certificates are issued and installed.
2. Neighbor router supports BGPsec (RFC 8205).
3. Operator understands the operational cost (BGPsec UPDATE messages are ~ 2x the size of BGP-4).
4. A and B neighbors agree on the BGPsec policy (origin validation, path validation).
5. Roll-over procedure is documented.

## Operational considerations (RFC 8209)

- **Message size**: BGPsec UPDATE carries signatures; total message size grows ~ 2x compared to BGP-4.
- **Performance**: signature generation is the dominant CPU cost. Hardware support (AES-NI, AVX) is recommended.
- **Roll-over**: per RFC 8211, dual-signing is supported; never disable the old key until the validation window elapses.
- **Failure modes**: if a router's cert is invalid, BGPsec sessions are torn down.
- **Fallback**: BGPsec can be deployed alongside BGP-4 in dual-stack mode; sessions roll back to BGP-4 if BGPsec fails.

## Observability

- BGPsec session count (gauge, by state).
- BGPsec UPDATE rate (counter).
- BGPsec signature validation failures (counter).
- Router key age (gauge, days since issuance).
- Roll-over state (gauge: pre, active, post, decommissioned).

## Sources

- RFC 8205 (BGPsec Protocol): `https://www.rfc-editor.org/rfc/rfc8205`
- RFC 8209 (Operational Considerations): `https://www.rfc-editor.org/rfc/rfc8209`
- RFC 8211 (Router Key Rollover): `https://www.rfc-editor.org/rfc/rfc8211`
- RFC 8208 (Algorithms): `https://www.rfc-editor.org/rfc/rfc8208`
- NIST RPKI Deployment Guide: `https://www.nist.gov/programs-projects/resource-public-key-infrastructure-rpki`
- BGPRESEARCH / IETF SIDR Working Group: `https://datatracker.ietf.org/wg/sidr/about/`
