# OpenAPI 3.2 itemSchema Streaming Contracts

**Issue:** Describing an unbounded NDJSON, JSON Text Sequence, multipart, or server-sent event stream as one buffered array hides per-item validation and streaming behavior.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use Media Type Object `itemSchema` to describe each independently processed item in a sequential streaming media type.
- Use `schema` for the complete content model; if both are present, verify that their meanings remain consistent.
- Select an accurate media type such as registered `application/json-seq`; do not silently equate formats with different delimiters.
- For server-sent events, model the parsed event fields and use content keywords when the `data` field embeds a format such as JSON.
- Document termination, reconnect, ordering, backpressure, malformed-item, and partial-consumption semantics outside the schema.

## Verification

- Validate individual items without buffering the full stream and test malformed records between valid records.
- Test chunk boundaries inside delimiters and multibyte characters because transport chunks are not item boundaries.
- Run contract tests against clients lacking OpenAPI 3.2 support and define an intentional fallback.

## Gotchas

- Verify source maturity and product support before making a normative claim.
- Keep secrets, tokens, personal data, and restricted evidence out of examples and logs.
- Reassess after material changes to scope, dependencies, or enforcement.

## Sources

- https://spec.openapis.org/oas/v3.2.0.html
- https://spec.openapis.org/registry/media-type/sequential_json
