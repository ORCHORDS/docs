---
title: DNSSEC Version Governance (RFC 4033, RFC 4034, RFC 4035, RFC 5155, RFC 6781, RFC 9276)
owner: ORCHORDS Platform Architecture
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: "IETF RFC 4033 (March 2005); RFC 4034 (March 2005); RFC 4035 (March 2005); RFC 5155 (March 2008); RFC 6781 (December 2011); RFC 9276 (August 2022); https://www.rfc-editor.org/rfc/rfc4033"
---

# DNSSEC Version Governance

## Scope

This card governs how ORCHORDS publishes, validates, signs, and rolls over
DNSSEC material for authoritative zones that belong to ORCHORDS, and how
validating resolvers inside ORCHORDS are configured. It binds the core
DNSSEC specification (RFC 4033, RFC 4034, RFC 4035), the NSEC3 hashed
denial-of-existence mechanism (RFC 5155), the DNSSEC operational practices
guide (RFC 6781), and the DNSSEC automation guidance (RFC 9276) into a
single reviewable artefact.

## Why DNSSEC matters here

DNS is the dependency graph for almost every other protocol. If an attacker
can spoof DNS responses, they can redirect certificate issuance, software
update channels, OAuth callback flows, and TLS handshakes. DNSSEC lets a
resolver cryptographically verify that the data it received is the same data
the zone owner published. For ORCHORDS, failure to validate DNSSEC inside
the platform and failure to sign authoritative zones both create attack
surface that is invisible to most monitoring tools because the answer still
resolves.

## Protocol identity

| Field | Value |
| --- | --- |
| Function | Cryptographic authentication of DNS data |
| Signing spec | DNSSEC-bis (RFC 4033 / 4034 / 4035) |
| Hash algorithms | SHA-1 (deprecated, RFC 9156), SHA-256 (DS digest 2, RFC 6605), SHA-384 (DS digest 4) |
| Signing algorithms | RSA/SHA-256 (8), RSA/SHA-512 (10), ECDSA P-256/SHA-256 (13), ECDSA P-384/SHA-384 (14), Ed25519 (15), Ed448 (16) |
| Denial of existence | NSEC (RFC 4034), NSEC3 / NSEC3PARAM (RFC 5155) |
| Trust anchors | DS records at parent, root trust anchor published by IANA |
| Key ceremony | Documented KSK / ZSK separation (RFC 6781 §3) |
| Recommended algorithm | Ed25519 (algorithm 15) for both KSK and ZSK where supported |

## Trust chain

Validation walks from a configured trust anchor (the root "K" key, or a
local trust anchor for enterprise zones) down through DS records at each
parent. A chain is `secure` only when every link from trust anchor to
response signature verifies under the algorithm and digest mandated for that
link. A chain that cannot be built or verified is `bogus` and the response
MUST be refused by validating resolvers.

## Key roles

- **KSK (Key Signing Key)** — signs only the DNSKEY RRset, including the
  DS record that the parent publishes. Long lifetime (often 1–2 years).
  Holds the secure entry point into the zone.
- **ZSK (Zone Signing Key)** — signs all other RRsets in the zone. Short
  lifetime (commonly 30–90 days) so routine rollovers do not require parent
  coordination.
- **CSK (Combined Signing Key)** — single key used for both roles,
  supported by some operators; allowed by RFC 6781 but not preferred.

## Algorithm and digest policy

ORCHORDS authorises the following DS digest pairs as of 2026-09-05:

- Digest 2 (SHA-256) — minimum acceptable for legacy compatibility.
- Digest 4 (SHA-384) — preferred for high-value zones where the parent
  supports it.
- Algorithms 13 (ECDSA P-256), 14 (ECDSA P-384), 15 (Ed25519), 16
  (Ed448) — preferred for new zones.
- Algorithms 1 (RSA/SHA-1) and 3 (DSA) — forbidden for new signing; phased
  out at rollover.
- Algorithm 7 (RSASHA1-NSEC3-SHA1) — forbidden under RFC 9156.

## NSEC vs NSEC3

- **NSEC** lists the next existing name in canonical order, which allows
  zone walking. Suitable for zones that do not require enumerated-name
  protection.
- **NSEC3 / NSEC3PARAM** hashes the next-existing name and adds salt and
  iteration count. Required when zone walking must be prevented.
- ORCHORDS default: NSEC3 with 0 additional iterations (RFC 9276 §4.2)
  and a 64-bit salt rotated with every ZSK rollover.

## Operational practices

- **Key rollovers.** Use the RFC 6781 "double-signing" approach: publish
  the new key alongside the old, wait for the TTL window plus a safety
  margin, then retire the old key. CSK and algorithm rollovers require a
  parent-DS change and a longer overlap window.
- **Algorithm rollover.** Treat as a structured migration with parent
  coordination; do not combine algorithm rollovers with KSK rollovers.
- **Negative response trust.** Validate NSEC or NSEC3 records, including
  the wildcard matching proof.
- **Signer clock skew.** Auditors MUST check signer clocks monthly; skew
  greater than the signature inception window blocks validation.
- **Zone-file integrity.** Signed zones are produced by an offline signer
  when practical; online signing is allowed only with strict ACLs and a
  captured binary log of every update.
- **Rollover runbook.** A signed, archived runbook must exist for every
  authoritative zone that contains the published DS record, signer host,
  ZSK schedule, and KSK schedule.

## Resolver policy

ORCHORDS-operated validating resolvers:

1. Maintain a current root trust anchor (RFC 5014); refresh from IANA
   monthly and via the in-band key roll when available.
2. Refuse `bogus` responses; never work around validation failures with
   `dnsset` overrides.
3. Surface per-zone validation state to the DNS observability stack with
   metrics for `secure`, `insecure`, `bogus`, `indeterminate`.
4. Apply per-client rate limits for bogus-query retries to limit damage
   from misbehaving clients.

## Deprecations and superseded work

- SHA-1 in DNSSEC — RFC 9156 deprecates it. Legacy chains remain valid
  only for grandfathered zones until rollover.
- NSEC3 high iteration counts — RFC 9276 §4.2 recommends 0 iterations.
- Wildcard answer trust — RFC 4592 clarifies; wildcard responses MUST have
  a valid wildcard signature.

## Reviewer checklist

- [ ] All ORCHORDS authoritative zones are signed with an allowed algorithm
      and digest pair.
- [ ] DS records at the parent match the active KSK and have not lapsed.
- [ ] ZSK rollover is automated and runs without parent coordination.
- [ ] NSEC3 zones use 0 additional iterations and rotate salt.
- [ ] Validating resolvers surface bogus / insecure / secure counters.
- [ ] No reliance on SHA-1 or algorithm 1 / 3 / 7.

## Source of truth

RFC 4033, RFC 4034, and RFC 4035 define DNSSEC-bis. RFC 5155 defines
NSEC3. RFC 6781 is the operational practices guide. RFC 9276 provides
DNSSEC automation guidance and recommends NSEC3 with 0 iterations.
