# MCP resource-link annotation rendering

**Issue:** MCP resource links and annotations are untrusted server metadata that can influence model context and UI.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Validate URI schemes, audience/priority bounds, fetch authorization, size/media type and provenance; require consent for external fetch.

## Tests

Private IP, redirects, huge resources, conflicting audience, stale link, unsupported client.

## Gotchas

Priority is advisory, not authority; linked content may contain prompt injection.

## Official sources

- https://modelcontextprotocol.io/specification/2025-06-18/server/resources
