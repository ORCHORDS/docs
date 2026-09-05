---
title: "Network Time Protocol Version 4 Version Guide (RFC 5905)"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 5905; https://www.rfc-editor.org/rfc/rfc5905"
---

# Network Time Protocol Version 4 Version Guide (RFC 5905)

## Scope

Reference card for Network Time Protocol version 4 (NTPv4) as defined in IETF RFC 5905 and selected updates. Used by operations, security, and platform teams when documenting time-service architecture, stratum hierarchy, and authentication of time sources.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | RFC 5905, "Network Time Protocol Version 4: Protocol and Algorithms Specification" |
| Status | Standards Track, Proposed Standard |
| Obsoletes | RFC 1305, RFC 1361, RFC 1769, RFC 2030, RFC 4330 |
| Selected updates | RFC 7822 (NTP Roughtime), RFC 8633 (NTP leap seconds), RFC 9109 (NTP authentication), draft-ietf-ntp-mode-6-cmds (control messages) |
| Stratum levels | 0 (reference clock) to 15; 16 (unsynchronized) |
| Modes | Symmetric (1, 2), Client (3), Server (4), Broadcast (5), NTP-control (6), NTP-private (7) |
| Selected extensions | Autokey (deprecated; informational RFC 5906), NTS (RFC 8915) |
| Verification source | https://www.rfc-editor.org/rfc/rfc5905 and successor RFCs |

## Plan

1. Identify time-service requirements (legal time, audit timestamp accuracy, log correlation).
2. Choose between NTPv4 (RFC 5905), PTP (IEEE 1588), or NTS-secured NTP (RFC 8915).
3. Map the stratum hierarchy: primary servers (stratum 1), secondary servers (stratum 2+), and clients.
4. Configure authentication where required (NTS preferred, otherwise IPsec / private network).
5. Document leap-second handling (RFC 8633) and operator response to leap-second events.

## Inputs

- Stratum 1 source plan (GPS, GNSS, atomic clock, or upstream time provider).
- Stratum 2 server topology and client access policy.
- Authentication material and NTS key rotation policy.
- Monitoring plan (offset, jitter, reachability, root dispersion).

## ORCHORDS Profile

This guide is used as a reference for NTP documentation and design reviews. It does NOT introduce protocol behavior beyond what RFCs specify. When an operational requirement exceeds what is captured here, escalate to a fresh RFC review and the IANA NTP parameters registry.

## Implementation Notes

- RFC 5905 is the baseline; prefer NTS (RFC 8915) over legacy Autokey (RFC 5906, deprecated).
- Restrict NTP service exposure; use access control lists and "notrust / limited / kod" directives where appropriate.
- Monitor root dispersion and offset; alerts should trigger when offset exceeds the SLO threshold.
- Reference implementation documentation and operator security guidance (RFC 7384, RFC 8633) apply to deployed servers.
- Leap-second smearing is an operator choice and must be documented.

## Companion Documents

- RFC 8915 (Network Time Security for NTP)
- RFC 7384 (NTP security analysis)
- RFC 8633 (NTP leap seconds)
- IANA NTP parameters registry
