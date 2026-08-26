# MCP structured tool-output backward compatibility

**Issue:** Structured tool output must remain compatible with clients that only understand textual content and with declared output schemas.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Negotiate capability, validate outputSchema, emit stable text fallback, version semantic changes, bound size.

## Tests

Old/new clients, invalid schema, partial failure, extra fields, oversized results.

## Gotchas

Schema-valid output can still be semantically wrong or hostile.

## Official sources

- https://modelcontextprotocol.io/specification/2025-06-18/server/tools
