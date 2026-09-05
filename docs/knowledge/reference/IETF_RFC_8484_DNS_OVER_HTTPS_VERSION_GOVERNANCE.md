---
title: "DNS-over-HTTPS Version Governance (RFC 8484)"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 8484; https://www.rfc-editor.org/rfc/rfc8484"
---

# DNS-over-HTTPS Version Governance (RFC 8484)

## Scope

Reference card for DNS-over-HTTPS (DoH) as defined by IETF RFC 8484. Used by network, platform, and operations teams when documenting stub-to-resolver transport encryption, DoH endpoint discovery, or DPI / middlebox posture. Treats RFC 8484 as the authoritative HTTP-based DNS transport, with RFC 7858 (DoT, port 853), RFC 8094 (DoH error reporting), RFC 8880 (DoH privacy profile), RFC 9250 (DoQ), RFC 9460 (SVCB / HTTPS RR for DoH endpoint discovery via `dns` service), RFC 9462 (DDR), RFC 9539 (DoH application profile), and RFC 9665 (DNS Error Reporting) as companion documents.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | RFC 8484, "DNS Queries over HTTPS (DoH)" |
| Status | Proposed Standard |
| Wire format | DNS wire format (RFC 1035) carried in HTTP request/response (RFC 9110) |
| Method | GET (with `?dns=` base64url param) or POST (application/dns-message body) |
| Media type | application/dns-message |
| Companion transports | RFC 7858 (DoT), RFC 9250 (DoQ), RFC 9460 / RFC 9462 (DoH IETF profile SVCB / DDR) |
| Verification source | https://www.rfc-editor.org/rfc/rfc8484 and IANA DoH registries |

## Plan

1. Identify the deployment context (DoH client: browser, mobile/OS stub resolver, application, DoH provider endpoint: enterprise / ISP / public resolver).
2. Map required behaviour against RFC 8484 § 4–§ 5 (HTTP method, request format, response format) and align with RFC 8880 privacy profile when handling user-bound DNS.
3. Capture operational requirements: DoH endpoint discovery (RFC 9460 / RFC 9462 / RFC 9539), DoH error reporting (RFC 8094 / RFC 9665), transport-level caching policy, and cache-from-URL hygiene.
4. Validate against the live IANA registries (DoH endpoints via IANA DoH Resolver Registry, HTTPS RR SvcParamKeys, SVCB Service Mode Keys, and the DNS Errors Reporting schema).

## Inputs

- DoH resolver list (IANA DoH Resolver Registry or enterprise-managed set) and authentication posture (RFC 8484 anonymous / RFC 9156 DoH privacy profile).
- URI template(s) per RFC 8484 § 4 (e.g., `https://dns.example/dns-query{?dns}`).
- Discovery posture (RFC 9460 SVCB / RFC 9462 DDR for `dns` service endpoint).
- Client cache hygiene (RFC 9499 DNS TTL handling; DoH-specific cache-from-URL reuse rules per RFC 8484 § 5).
- DoH-specific logging and error reporting (RFC 8094 / RFC 9665).

## ORCHORDS Profile

This guide is used as a reference when reviewing DoH deployment documentation or designing encrypted DNS posture. It does NOT introduce protocol behaviour beyond what the RFCs and IANA registries specify. When a behavioural rule that is not captured here is required by a DoH operation, escalate to a fresh review against the current RFC and the relevant IANA registry.

## Implementation Notes

- Use DoH for resolver-stitching only where it meaningfully improves privacy / integrity vs plaintext UDP/53 (RFC 7858 / RFC 8094).
- Where DoH is offered, pair with RFC 9460 `dns` SvcParamKeys and RFC 9462 DDR for authenticated endpoint discovery; do not rely on a per-app URL alone.
- For user-bound DNS, follow RFC 8880 (DoH privacy profile); for privacy posture in browsers, refer to RFC 9539.
- For DoH endpoints, follow RFC 8094 error reporting and RFC 9665 master-schema integration; treat `application/dns-message` errors as DNS errors and surface as such.
- Apply RFC 9499 caching rules to ensure DNS DoH responses are not cached beyond the record's original TTL; do not use the HTTP cache for DNS data without a deliberate invalidation plan.
- Pair DoH with DNSSEC validation per RFC 4033; DoH preserves but does not replace DNSSEC integrity.
- For interop considerations, never run DoH alongside plaintext resolvers on the same logical network without an explicit policy.

## Companion Documents

- RFC 7858 (DoT, port 853)
- RFC 8094 (DoH Error Reporting)
- RFC 8880 (DoH Privacy Profile)
- RFC 9110 (HTTP Semantics, underlying HTTP transport)
- RFC 9156 (DoH Privacy Profile for Stub Resolvers, deprecated by RFC 9539)
- RFC 9460 / RFC 9462 / RFC 9539 (DoH service discovery / DDR / profile)
- RFC 9499 (DNS TTL-based caching semantics)
- RFC 9665 / RFC 9845 (DNS Error Reporting / Extended DNS Error)
- IANA DoH Resolvers / SvcParamKeys / Service Mode Keys / DDDS Application Tags
