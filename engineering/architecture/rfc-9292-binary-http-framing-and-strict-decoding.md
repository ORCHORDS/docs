# RFC 9292 Binary HTTP Framing and Strict Decoding

**Issue:** Encapsulating HTTP outside an HTTP connection needs deterministic framing that preserves semantics without inheriting ambiguous text parsing.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use `message/bhttp` only where an application must carry HTTP semantics independent of a live HTTP protocol.
- Select known-length framing when sizes are available and indeterminate-length framing when streaming generation is required.
- Validate framing indicator, control data, field names and values, length prefixes, content terminators, and zero-only padding strictly.
- Treat invalid messages as terminal and do not process further beyond safe error handling.
- Apply explicit resource limits even though the wire format permits very large sections.

## Verification

- Round-trip requests, informational plus final responses, trailers, empty content, permitted truncation, and padding.
- Fuzz invalid framing indicators, oversized lengths, zero-length field names, uppercase or malformed field names, and nonzero padding.
- Test incremental decoders that discover invalid input only after partial delivery and ensure no side effect commits early.

## Gotchas

- Confirm the cited feature or standard edition remains current before relying on it.
- Keep secrets, personal data, and restricted evidence out of examples and logs.
- Reassess after scope, implementation, or policy changes.

## Sources

- https://www.rfc-editor.org/rfc/rfc9292.html
