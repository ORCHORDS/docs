---
title: "HTTP Semantics Version Guide (RFC 9110)"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 9110; https://www.rfc-editor.org/rfc/rfc9110"
---

# HTTP Semantics Version Guide (RFC 9110)

## Scope

Reference card for HTTP semantics as defined in IETF RFC 9110, which consolidates and replaces RFC 7230, RFC 7231, RFC 7232, RFC 7233, RFC 7234, RFC 7235, RFC 7236, RFC 7237, RFC 7238, RFC 7239, RFC 7240, and others. Used by API, platform, and security teams when documenting HTTP message semantics, request methods, status codes, headers, content negotiation, and authentication.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | RFC 9110, "HTTP Semantics" |
| Status | Internet Standard (along with RFC 9112) |
| Companion | RFC 9112 (HTTP/1.1 message framing and transfer coding) |
| Request methods | GET, HEAD, POST, PUT, DELETE, CONNECT, OPTIONS, TRACE (and conditional, range, partial) |
| Status code classes | 1xx Informational, 2xx Successful, 3xx Redirection, 4xx Client Error, 5xx Server Error |
| Selected headers | Accept, Accept-Charset, Accept-Encoding, Accept-Language, Authorization, Cache-Control, Content-Disposition, Content-Length, Content-Type, Date, ETag, Expires, Host, If-Match, If-Modified-Since, If-None-Match, Last-Modified, Location, Range, Retry-After, Server, Set-Cookie, Transfer-Encoding, Vary, Via, WWW-Authenticate |
| Selected authentication | Basic (RFC 7617), Digest (RFC 7616), Bearer (RFC 6750) |
| Verification source | https://www.rfc-editor.org/rfc/rfc9110 |

## Plan

1. Identify the HTTP version(s) in scope (HTTP/1.1 per RFC 9112, HTTP/2 per RFC 9113, HTTP/3 per RFC 9114).
2. Document request/response semantics for each endpoint family, including method, status codes, and headers.
3. Plan content negotiation (Accept, Accept-Language, content type), range requests, and conditional requests.
4. Map authentication (RFC 9110 §11) to credentials scheme (Basic, Digest, Bearer).
5. Document caching behavior (RFC 9111) and cache-control directives.

## Inputs

- Resource model and URI design.
- Required HTTP methods and their semantic guarantees.
- Status code conventions per error class.
- Authentication and authorization model.
- Caching requirements (private vs shared, freshness lifetime).

## ORCHORDS Profile

This guide is used as a reference for HTTP API documentation and design reviews. It does NOT introduce protocol behavior beyond what RFCs specify. When an operational requirement exceeds what is captured here, escalate to a fresh RFC review and the IANA HTTP registry.

## Implementation Notes

- RFC 9110 defines HTTP semantics independent of version; pair with RFC 9112 (HTTP/1.1), RFC 9113 (HTTP/2), or RFC 9114 (HTTP/3) for transport-specific concerns.
- Authentication: prefer Bearer (RFC 6750) over Basic for API contexts; Digest (RFC 7616) is acceptable when Bearer is unavailable.
- Status code selection must reflect the actual outcome; do not use 200 for failures.
- Use cache directives per RFC 9111; private caches and CDN caches may have different freshness requirements.
- Method semantics (RFC 9110 §9) — PUT, POST, DELETE, PATCH, OPTIONS, HEAD — must align with the resource model.

## Companion Documents

- RFC 9111 (HTTP Caching)
- RFC 9112 (HTTP/1.1)
- RFC 9113 (HTTP/2)
- RFC 9114 (HTTP/3)
- RFC 6750 (Bearer)
- IANA HTTP registry
