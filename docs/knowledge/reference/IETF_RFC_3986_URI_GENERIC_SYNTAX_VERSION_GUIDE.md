---
title: "IETF RFC 3986 URI Generic Syntax Version Guide"
standard: "RFC 3986"
standard_status: "Internet Standard (STD 66)"
publisher: "Internet Engineering Task Force (IETF)"
authors: "T. Berners-Lee, R. Fielding, L. Masinter"
category: "reference"
subcategory: "uri-syntax"
canonical_url: "https://datatracker.ietf.org/doc/html/rfc3986"
obsoletes: "RFC 2732, RFC 2396"
category_iana: "standards"
status: "approved"
classification: "public"
audience: "engineers"
last_reviewed: "2026-09-04"
---

# IETF RFC 3986 URI Generic Syntax Version Guide

## 1. Purpose

RFC 3986 defines the generic syntax of Uniform Resource Identifiers (URIs) —
both Uniform Resource Locators (URLs) and Uniform Resource Names (URNs). It
is Internet Standard 66 and the foundation of HTTP, WebSockets, OAuth, OIDC,
and nearly every modern API. This guide pins ORCHORDS adoption of RFC 3986 for
all resource addressing, with a strict subset for production URLs.

## 2. URI Components

```
URI         = scheme ":" hier-part [ "?" query ] [ "#" fragment ]
hier-part   = "//" authority path-abempty / path-absolute / path-rootless / path-empty
authority   = [ userinfo "@" ] host [ ":" port ]
path        = path-abempty / path-absolute / path-noscheme / path-rootless / path-empty
```

## 3. Reference Profile Adopted by ORCHORDS

| Component | Decision | Rationale |
|---|---|---|
| Scheme | Lowercase letters; registered in IANA URI scheme registry | RFC 3986 §3.1 |
| Authority host | Lowercase DNS name or IP literal | RFC 3986 §3.2.2; case-insensitive comparison |
| Port | Omit if default for scheme | RFC 3986 §3.2.3 |
| Userinfo | Disallowed in public APIs | Deprecated for credentials in URL |
| Path | Percent-encoded only when necessary | RFC 3986 §3.3 |
| Query | `application/x-www-form-urlencoded` percent-encoding | RFC 3986 §3.4 |
| Fragment | Never transmitted to server | RFC 3986 §3.5 |

## 4. Percent-Encoding Quick Reference

- Reserved characters that MUST be percent-encoded in their component context:
  space (encode as `%20` or `+` in `application/x-www-form-urlencoded`), `#`,
  `?`, `<`, `>`, `"`, `{`, `}`, `|`, `\`, `^`, `` ` ``, `[`, `]`.
- Unreserved characters that NEVER need encoding: `A-Z a-z 0-9 - . _ ~`.
- UTF-8 bytes for non-ASCII characters: percent-encode each byte.

## 5. Concrete Examples

```
https://example.com/
https://example.com:8443/secure
https://user:[email protected]/path?q=1&r=2#frag
urn:isbn:0451450523
mailto:[email protected]
```

## 6. Path Segment Encoding (RFC 3986 §3.3 + RFC 3987 for IRI)

When building URLs programmatically:

```javascript
// Correct: encode each path segment, then join
const segs = ["v1", "users/42", "profile image.jpg"];
const url = "https://api.example.com/" +
  segs.map(s => encodeURIComponent(s).replace(/%2F/g, "%2F")).join("/");
```

## 7. Forbidden Constructs

- Raw spaces, raw `<` `>` `"` `{` `}` in any component.
- Mixed-case scheme or host in canonical form.
- Backslash `\` as path separator (Windows paths).
- Empty scheme with authority (`//host/path` is a valid network-path reference but must be resolved against a base URI; do not emit as absolute URL).
- Unicode characters in URI; use IRI → URI conversion via UTF-8 percent-encoding.

## 8. Comparison and Equivalence

RFC 3986 §6.2.2 normalization:

1. Case normalization: scheme and host lowercased; case-sensitive hex digits `%XX` uppercased.
2. Percent-encoding normalization: decode unreserved characters that have been encoded (`%41` → `A`).
3. Path segment normalization: remove `..` and `.` where safe.
4. Scheme-based normalization: HTTP `301/302` redirects from non-`www` to `www`.

ORCHORDS applies rules 1–3 before storing canonical URLs; rule 4 is an edge-router concern.

## 9. Related Standards

- **RFC 3987** — Internationalized Resource Identifiers (IRIs).
- **RFC 6570** — URI Template (e.g. `{var}`, `{?var*}`).
- **RFC 8141** — URN Syntax (supersedes RFC 2141).
- **RFC 8615** — URI scheme `urn:uuid:` and other well-known URI schemes.
- **WHATWG URL** — modern browser-side parser used by `URL`/`URLSearchParams`; differs in some edge cases (e.g. trailing whitespace).

## 10. Version History

| Year | Action |
|---|---|
| 1994 | RFC 1630 — URI generic syntax (initial) |
| 1995 | RFC 1738 / RFC 1808 — URLs and relative URLs |
| 1998 | RFC 2396 — URI generic syntax (predecessor) |
| 2005 | RFC 3986 — current Internet Standard 66 |
| 2026-09 | ORCHORDS reference card last reviewed |
