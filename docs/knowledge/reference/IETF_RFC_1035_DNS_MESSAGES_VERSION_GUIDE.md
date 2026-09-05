---
title: "DNS Messages Version Guide (RFC 1035)"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 1035; https://www.rfc-editor.org/rfc/rfc1035"
---

# DNS Messages Version Guide (RFC 1035)

## Scope

Reference card for the Domain Name System message format as defined by IETF RFC 1035. Used by network, platform, and operations teams when documenting DNS resolver/authoritative-server behaviour, zone serial handling, or message parsing. Treats RFC 1035 as the baseline message format, with RFC 4033/4034/4035 (DNSSEC), RFC 6891 (EDNS0), RFC 7766 (DNS over TCP), RFC 8484 (DNS over HTTPS), RFC 9250 (DNS over QUIC), RFC 9460 (SVCB/HTTPS RR), RFC 9614 (XFR-incremental), RFC 9665 (DNS error reporting), and RFC 9845 (DNS error extended information) as selected updates.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | RFC 1035, "Domain Names — Implementation and Specification" |
| Status | Internet Standard |
| Message header (RFC 1035 § 4.1.1) | 12-byte fixed header: ID, QR, OPCODE, AA, TC, RD, RA, Z, RCODE, QDCOUNT, ANCOUNT, NSCOUNT, ARCOUNT |
| OpCodes | 0 Query, 1 IQUERY (obsolete), 2 Status, 4 Notify, 5 Update, 6 DSO |
| RCODEs (RFC 1035 + RFC 6891 + RFC 8914 + RFC 9210) | 0–23 (DNS RCODE registry) |
| RR types | A, NS, CNAME, SOA, PTR, MX, TXT, AAAA, SRV, OPT, HTTPS, SVCB, … (IANA RR Type registry) |
| Verification source | https://www.rfc-editor.org/rfc/rfc1035 and IANA DNS registries |

## Plan

1. Identify the deployment context (recursive resolver, authoritative server, forwarder, stub resolver, primary/secondary transfer).
2. Map required behaviour against RFC 1035 § 4–§ 8 (message format, master file format, name compression, resource records, transport).
3. Capture operational requirements: EDNS0 (RFC 6891) buffer sizing, DNSSEC validation chain (RFC 4033), DNS-over-TCP retry (RFC 7766), transport selection (RFC 8499 / RFC 9250), and zone-transfer policy (AXFR per RFC 1035 § 6.2, IXFR per RFC 1995 / RFC 9614).
4. Validate against the live IANA DNS parameters registries (OpCodes, RCODEs, RR types, EDNS options).

## Inputs

- Zone serial policy (SOA SERIAL cadence, increment rule, multi-master posture).
- Resource record set in scope (A, AAAA, MX, TXT, SRV, SVCB, HTTPS, CAA, TLSA, DS, DNSKEY).
- DNSSEC policy (algorithm list per RFC 8624, NSEC/NSEC3 selection, signature cadence).
- Transport policy (UDP port 53, TCP port 53 fallback per RFC 7766, DoH per RFC 8484, DoQ per RFC 9250, DoT per RFC 7858).
- Privacy/recursive resolver policy (RFC 9076, RFC 9156).

## ORCHORDS Profile

This guide is used as a reference when reviewing DNS zone documentation or designing resolver / authoritative infrastructure. It does NOT introduce protocol behaviour beyond what the RFCs and IANA registries specify. When a behavioural rule that is not captured here is required by a DNS operation, escalate to a fresh review against the current RFC and the relevant IANA DNS registry.

## Implementation Notes

- RFC 1035 defines message framing; current defaults must align with RFC 6891 (EDNS0) and RFC 7766 (TCP fallback) for queries larger than 512 bytes or for AXFR/IXFR transfers.
- DNSSEC: use algorithm selection per RFC 8624; validate chains to a trust anchor; treat BIND-style key rollovers with the parent zone.
- DNSSEC end-of-trust-zone signalling per RFC 9615 (Generalized DNSNOTIFY) when applicable.
- DNS error reporting: align log surfaces with RFC 9665 (DNS Error Reporting) and extend per RFC 9845 (DELEG, DS, DNSKEY, etc.) on validation fail.
- For service discovery, use SVCB / HTTPS RR per RFC 9460; pair with ESNI / ECH (RFC 9578, RFC 9680) where supported by the resolver.

## Companion Documents

- RFC 4033 / 4034 / 4035 (DNSSEC)
- RFC 6891 (EDNS0)
- RFC 7766 (DNS over TCP)
- RFC 8484 (DoH)
- RFC 9250 (DoQ)
- RFC 9460 (SVCB / HTTPS RR)
- RFC 9614 (XFR-incremental over DoT/UDP)
- RFC 9665 (DNS Error Reporting)
- RFC 9845 (Extended DNS Error Codes)
- IANA DNS OpCodes / RCODEs / RR Types / EDNS option registries
