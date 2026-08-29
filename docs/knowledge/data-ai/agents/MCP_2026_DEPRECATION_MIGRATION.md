# MCP 2026 Deprecation and Migration Planning

## Purpose

MCP 2026-07-28 introduces a formal deprecation policy with a minimum twelve-month window and deprecates several legacy protocol surfaces, including Roots, Sampling, Logging, Dynamic Client Registration, and the legacy HTTP+SSE transport.

## Migration guidance

1. Inventory which protocol revision and deprecated features each client/server still depends on.
2. Prefer new implementations that target the modern 2026-07-28 behaviors instead of adding fresh dependencies on deprecated surfaces.
3. Run dual-version compatibility only where it is necessary and tested.
4. Make protocol-era selection explicit so an operation cannot silently cross from modern to legacy semantics.
5. Track removal deadlines and SDK migration notes as release dependencies.
6. Test downgrade and fallback paths before relying on them in production.
7. Remove compatibility code after the supported migration window instead of leaving permanent ambiguous behavior.

## Sources

- Model Context Protocol — 2026-07-28 specification release: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- MCP TypeScript SDK — supporting protocol revision 2026-07-28: https://ts.sdk.modelcontextprotocol.io/v2/migration/support-2026-07-28

## Scope note

The deprecation window is protocol policy, not a guarantee that every SDK or deployment will retain every legacy API for the same duration. Check the implementation's own release notes as well.
