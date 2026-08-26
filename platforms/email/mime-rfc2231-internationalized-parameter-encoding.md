# MIME RFC 2231 Internationalized Parameter Encoding

**Issue:** Non-ASCII or long attachment filenames are placed directly in MIME parameters or encoded as headers, producing mojibake, truncated names, unsafe reconstruction, and inconsistent client behavior.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Control pattern

For MIME parameters such as `filename`, use RFC 2231 extended parameter syntax with declared charset/language and percent-encoded octets. Use numbered continuations only when required, keep indices contiguous from zero, and distinguish extended segments (`*0*=`) from plain ones. Generate a conservative ASCII fallback where interoperability policy requires it.

Parse parameters as a bounded structured field: unfold the header, collect segments by base name, reject duplicate/conflicting indices, cap segment count and decoded length, percent-decode once, then decode the declared charset under an allow-list. Sanitize the resulting display filename separately from filesystem storage; never use it as a path.

## Verification

Test ASCII and UTF-8 names, spaces, percent signs, language tags, long continuations, mixed encoded/plain segments, missing and repeated indices, unknown charset, invalid escapes, header folding, conflicting `filename` and `filename*`, path separators, control characters, and normalization collisions. Round-trip through target mail clients.

## Gotchas

RFC 2047 encoded-words are not a substitute inside MIME parameter values. Percent-decoding twice is dangerous. A decoded filename remains untrusted input. Client precedence between fallback and extended values can differ, so security decisions must not depend on the displayed name.

## Sources

- [IETF RFC 2231 — MIME Parameter Value and Encoded Word Extensions](https://datatracker.ietf.org/doc/html/rfc2231)
- [IETF RFC 2045 — MIME Part One](https://datatracker.ietf.org/doc/html/rfc2045)
