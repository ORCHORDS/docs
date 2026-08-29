# MCP Tool Schemas with JSON Schema 2020-12

## Purpose

The MCP 2026-07-28 revision adopts full JSON Schema 2020-12 support for tool schemas. This gives tool authors a richer, standardized vocabulary for describing accepted inputs and structured outputs.

## Guidance

1. Keep tool schemas as narrow as the operation requires; avoid permissive catch-all objects when stronger constraints are known.
2. Validate tool arguments on the server even when the client or model already validated them.
3. Use required properties, enums, numeric/string bounds, and structured object shapes to make invalid calls fail early.
4. Treat schema descriptions as documentation, not authorization.
5. Version breaking schema changes deliberately so cached tool catalogs and clients do not silently misinterpret them.
6. Test generated arguments against the same schema used at execution time.
7. Avoid embedding secrets, internal identifiers, or sensitive examples in public tool schemas.

## Sources

- Model Context Protocol — 2026-07-28 specification release candidate and migration overview: https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/
- JSON Schema — Draft 2020-12: https://json-schema.org/draft/2020-12

## Scope note

Schema validation improves interoperability and input quality. Business authorization and semantic safety checks still belong in the tool implementation.
