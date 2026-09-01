---
title: "OWASP API Security API7:2023 SSRF Verification"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# OWASP API Security API7:2023 SSRF Verification

## Pinned source and scope
OWASP API Security Top 10 **2023**, **API7:2023 Server Side Request Forgery**. This article uses the named version and identifiers; do not combine evidence from another edition without a migration record.

## Control interpretation
Prefer server-side destination identifiers. If URLs are required, parse once, restrict scheme/port, reject credentials and fragments when irrelevant, resolve all A/AAAA answers, block loopback/link-local/private/reserved/metadata ranges, connect to the validated address while preserving intended TLS identity, and revalidate every redirect. Apply egress policy below application code.

## Domain-specific procedure
Test decimal/octal/hex IPv4 forms, IPv4-in-IPv6, zero, localhost aliases, trailing dots, userinfo confusion, IDNs, DNS rebinding, multiple answers, redirect chains, proxy environment variables, gopher/file schemes, and cloud metadata addresses. Capture DNS answers and actual socket destination, not only the input validator result.

## Evidence and decision
Retain original URL, parsed fields, DNS answers over time, validated addresses, actual connection peer, redirect hops, proxy path, and egress decision. Validator success without peer evidence is insufficient.

## Failure modes
Regex parsing, checking only the first DNS answer, following unchecked redirects, and allowing metadata through an outbound proxy are failures.

## Sources
- [Pinned canonical source](https://owasp.org/API-Security/editions/2023/en/0xa7-server-side-request-forgery/)
