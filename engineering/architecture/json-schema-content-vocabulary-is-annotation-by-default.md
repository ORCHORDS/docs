# JSON Schema content vocabulary is annotation by default

**Issue:** A schema with `contentEncoding`, `contentMediaType`, or `contentSchema` can be mistaken for a guarantee that encoded content was decoded and validated.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Treat Draft 2020-12 content keywords as annotations unless an explicitly qualified application layer performs decoding and nested validation.
- Validate the outer JSON instance first, then decode with strict size, expansion, media-type, and time budgets.
- Apply `contentSchema` only after a trusted mapping converts the decoded media type into the JSON data model.
- Require `contentMediaType` when relying on `contentSchema`; the specification says the latter should be ignored without it.
- Allowlist encodings and media types, and keep parsers for active content outside privileged processes.

## Verification

Test malformed encodings, valid encodings with invalid nested content, decompression expansion, mislabeled media types, unsupported parsers, and validators that ignore all content annotations.

## Gotchas

Implementations must not decode or validate encoded content by default. A passing JSON Schema result therefore says nothing about whether a base64 string is valid, safe, or conforms to its nested schema unless the application adds that processing.

## Official sources

- [JSON Schema Draft 2020-12 validation vocabulary](https://json-schema.org/draft/2020-12/json-schema-validation)
