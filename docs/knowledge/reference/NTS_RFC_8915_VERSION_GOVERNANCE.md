---
title: Network Time Security Version Governance (RFC 8915, RFC 9337)
owner: ORCHORDS Platform Architecture
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: "IETF NTP Working Group; RFC 8915 (September 2020); RFC 9337 (January 2023); https://www.rfc-editor.org/rfc/rfc8915"
---

# Network Time Security Version Governance

## Scope

This card governs how ORCHORDS produces, distributes, and authenticates
time on platforms that depend on Network Time Protocol (NTP, RFC 5905) and
its successor messaging model (NTPv5 draft). It binds the Network Time
Security protocol (RFC 8915), the NTS Key Establishment (NTS-KE) TLS
profile (RFC 9337), and the underlying NTP specification to a single
reviewable artefact.

## Why authenticated time matters here

Time is the basis for audit log correlation, certificate validity windows,
single-use nonce construction, distributed transaction ordering, and
incident reconstruction. If a host's clock can be moved by an attacker, every
cryptographic and forensic control built on that clock becomes suspect.
Plain NTP has no integrity protection, so any on-path adversary can shift a
client's clock by tens of seconds or more without detection. NTS exists to
close that gap.

## Protocol identity

| Field | Value |
| --- | --- |
| Function | Authenticated time synchronisation over NTP |
| Spec | RFC 8915 (NTS), RFC 9337 (NTS-KE TLS profile) |
| Key establishment | TLS 1.2 / 1.3 over TCP port 4460 |
| Time transport | NTPv4 (RFC 5905) over UDP port 123 |
| Cookie format | RFC 8915 §6; AEAD-encrypted with negotiated key |
| Default AEAD | AES-128-SIV, AES-SIV (RFC 5297) recommended; AEAD_AES_128_GCM_SIV (RFC 8452) acceptable |
| Server identity | TLS certificate; SAN dNSName MUST match the NTS-KE host |
| Client identity | None required for anonymous mode; per-client keys optional |

## Architectural layers

NTS separates the slow-path key establishment from the fast-path time
exchange:

1. **NTS-KE (key establishment).** TLS 1.3 handshake at TCP 4460 with
   mutual authentication against a trusted root. The server returns one or
   more IP addresses for the NTP time source, the negotiated AEAD algorithm,
   a new NTS cookie, and a key for the cookie.
2. **NTP time exchange.** The client sends NTPv4 packets over UDP 123 with
   the NTS cookies attached as extension fields. The server validates the
   cookie, replies with the current time plus a fresh cookie.
3. **Cookie rotation.** The client MUST rotate the cookie before reaching
   zero remaining cookies, and SHOULD request a new cookie in the same UDP
   packet that contains the last cookie to keep latency stable.

## Threat model

NTS specifically defends against:

- On-path attackers shifting the client clock.
- Off-path attackers injecting forged NTP replies.
- Server impersonation via forged certificates.

NTS does not defend against:

- Coercion attacks where the attacker forces the client to stop using NTS.
- Pathological latency injection that does not shift the final estimate but
  destabilises the filtering algorithm.
- Compromise of the underlying OS clock; NTS only authenticates the wire.

## Server policy

ORCHORDS-operated NTS servers:

- Listen on UDP 123 for NTP and TCP 4460 for NTS-KE.
- Terminate NTS-KE on a TLS profile that requires TLS 1.3 and AEAD-only
  cipher suites.
- Publish a certificate with a SAN dNSName that matches the public
  NTS-KE hostname.
- Maintain an IPv4 and IPv6 time source address.
- Apply rate limiting per source prefix to dampen amplification risk.
- Emit structured logs of NTS-KE handshakes and cookie requests for audit.

## Client policy

ORCHORDS-operated NTS clients:

- Configure at least three independent NTS sources (RFC 8633 §3.4 — see
  also the local clock filter recommendations of RFC 8633).
- Reject NTP responses that do not carry a valid NTS extension.
- Reject cookies older than the negotiated lifetime.
- Refuse to fall back to unauthenticated NTP without explicit operator
  approval and a captured event.
- Emit metrics for `nts_ke_success`, `nts_ke_fail`, `cookie_lifetime`,
  `offset_seconds`.

## Key management

- Server TLS keys are rotated annually, or immediately on suspected
  compromise, with a documented handover window during which both keys
  are valid.
- Server private keys never leave the NTS-KE host; if HSM is used, the
  key is generated inside the HSM and is referenced only by handle.
- Cookie keys are rotated weekly. Reusing a cookie key after rotation is
  treated as an incident.

## Interactions with other controls

- **PKI.** The NTS-KE server certificate chain MUST terminate at a
  publicly trusted root. Self-signed roots are not permitted for public
  NTS endpoints.
- **Monitoring.** NTS failure rates are tracked in the SLO dashboard
  alongside NTP offset.
- **DNSSEC.** NTS-KE hostnames are signed and validated end-to-end so
  that a downgrade attack on DNS does not redirect the client to a
  hostile NTS source.

## Deprecations and superseded work

- **Symmetric key NTP (RFC 5905 §6).** Permitted only on isolated
  control networks where the symmetric key is out-of-band provisioned;
  NTS replaces it everywhere else.
- **Autokey (RFC 5906).** Historic, deprecated; not deployed.
- **NTPv3 and earlier.** Disallowed.

## Reviewer checklist

- [ ] Public NTS servers support TLS 1.3 and reject TLS 1.2 / 1.1.
- [ ] NTS-KE certificate SAN matches the public hostname.
- [ ] Cookies rotate before expiry with monitoring alerts.
- [ ] Cookie keys rotate on schedule and on suspected compromise.
- [ ] Clients refuse to fall back silently to unauthenticated NTP.
- [ ] NTS metrics feed the platform SLO dashboard.

## Source of truth

RFC 8915 defines NTS. RFC 9337 codifies the NTS-KE TLS profile.
RFC 5905 defines NTPv4. RFC 8633 provides NTP best-current-practice.
