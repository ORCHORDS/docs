# HTTP Structured Fields RFC 9651 parsing

**Issue:** Bespoke HTTP header parsers disagree on whitespace, quoting, duplicate lines, Unicode, and malformed input.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Use RFC 9651 for newly defined structured headers/trailers. It is an Internet Standards Track RFC and obsoletes RFC 8941.

## Controls

Specify the entire field as List, Dictionary, or Item; define semantics and constraints; use compliant parser/serializer libraries; preserve parameters and unknown extensions; enforce size limits outside the RFC minimums; choose fail-message or ignore-field behavior explicitly on parse failure.

## Verification

Run RFC examples plus malformed escapes, split lines, duplicate dictionary keys, boundary integers/decimals, dates, display strings, and intermediary line combination. Round-trip abstract values, not raw text equality.

## Gotchas

Only fields explicitly defined as Structured Fields use these rules. Partial-field adoption is invalid. Strings and tokens are distinct. Malformed input handling is intentionally strict.

## Sources

- [RFC 9651](https://www.rfc-editor.org/info/rfc9651/)
