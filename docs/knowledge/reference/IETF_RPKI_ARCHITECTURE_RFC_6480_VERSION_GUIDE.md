---
title: "RPKI Architecture Version Guide (RFC 6480)"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 6480; https://www.rfc-editor.org/rfc/rfc6480"
---

# RPKI Architecture Version Guide (RFC 6480)

## Scope

Reference card for the Resource Public Key Infrastructure (RPKI) architecture as defined by IETF RFC 6480. Used by network, registry, and operations teams when documenting RPKI repository design, certificate issuance (RFC 6487), ROA publication (RFC 6482), validator deployment (RFC 6810), or origin-validation posture (RFC 7115 / RFC 9319 / RFC 8210). Treats RFC 6480 as the authoritative architecture, with RFC 6481–6487, RFC 6493, RFC 6810, RFC 6916, RFC 7093, RFC 7115, RFC 8210, RFC 8893, RFC 9319, RFC 9328, RFC 9582, and the RPKI Signed Checklist (draft-ietf-sidrops-rpki-rsc) as companion documents.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | RFC 6480, "An Infrastructure to Support Secure Internet Routing" |
| Status | Informational; companion: RFC 6481 (Tree), RFC 6482 (ROA), RFC 6483 (CRL profile), RFC 6487 (Certificate Profile), RFC 6810 (RPKI to Router), RFC 8210 (Routability / Signed Objects), RFC 8893 (BGPsec), RFC 9319 (Operational Practices), RFC 9328 (Manifest), RFC 9582 (Algorithm Agility) |
| Repository | rsync (RFC 5781, RFC 8181), RRDP (RFC 8182) |
| Trust Anchor | trust-anchor-cer; TAL (RFC 7730) |
| Verification source | https://www.rfc-editor.org/rfc/rfc6480 and IANA RPKI repositories |

## Plan

1. Identify the deployment context (RIR / NIR / registry operator, hosting-provider ROA publisher, ISP/RP validator, AS operator with BGPsec).
2. Map required behaviour against RFC 6480 § 2–§ 4 (architecture goals, entities, repositories) and the certificate / ROA / manifest / CRL profiles.
3. Capture operational requirements: RRDP + rsync dual publication (RFC 8182), manifest cadence (RFC 9328), CRL cadence (RFC 6483), algorithm selection per RFC 9582, and routing-policy pair with ROA-based origin validation (RFC 7115).
4. Validate against the live IANA registries (RPKI Signed Object Templates, RPKI Cryptographic Algorithms, BGPsec algorithms, and the five RIR trust anchors).

## Inputs

- Certificate issuance policy (RFC 6487 § 2 — manifest, EE, CA, BGPsec, ROA).
- ROA coverage (RFC 6482) — prefix, maxLength, ASN.
- Repository publication (rsync RFC 5781, RRDP RFC 8182; HTTPS RRDP client profile per RFC 9495).
- Validator deployment (RFC 6810 — RPKI to Router protocol, RFC 8210 — Routability / Signed Objects, RFC 8893 — BGPsec router profile).
- Routing policy (RFC 7115 — origin-validation states: Valid, Invalid, NotFound, Unknown).

## ORCHORDS Profile

This guide is used as a reference when reviewing RPKI documentation or designing registry / validator / BGPsec infrastructure. It does NOT introduce protocol behaviour beyond what the RFCs and IANA registries specify. When a behavioural rule that is not captured here is required by an RPKI operation, escalate to a fresh review against the current RFC and the relevant IANA registry.

## Implementation Notes

- Publish RPKI objects over RRDP (RFC 8182) and rsync (RFC 8181) — both required for interoperability, not either/or.
- Use SHA-256 with RSA (2048+) for ROAs and certificates per RFC 9582; rotate according to algorithm-agility guidance and current registry operator policy.
- Always pair ROA publication (RFC 6482) with origin-validation at the BGP speaker (RFC 6810 / RFC 7115); treat "Invalid" routes as dropped per RFC 9319 § 4.
- For BGPsec (RFC 8205 / RFC 8893), align capability advertisement with peer capabilities; do not assume peers speak BGPsec.
- Maintain CRL publication (RFC 6483) and manifest publication (RFC 9328) — a stale manifest is treated as a publication failure per RFC 9328 § 4.

## Companion Documents

- RFC 6481 (RPKI Tree)
- RFC 6482 (ROA)
- RFC 6483 (CRL)
- RFC 6487 (Certificate / Manifest Profile)
- RFC 6810 / RFC 8210 (RPKI to Router / Routability)
- RFC 6916 / RFC 7093 (Production-readiness, Ghostbusters)
- RFC 7115 (Origin Validation)
- RFC 7730 (TAL)
- RFC 8181 / RFC 8182 (rsync / RRDP)
- RFC 8205 / RFC 8893 / RFC 9495 (BGPsec & HTTPS RRDP)
- RFC 9319 (Operational Practices)
- RFC 9328 (Manifest)
- RFC 9582 (Algorithm Agility)
- IANA RPKI Signed Object Templates / Cryptographic Algorithms / BGPsec algorithms
