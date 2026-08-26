# ESLint MCP server trust boundary

**Issue**

Exposing lint capabilities through an MCP server lets agent-supplied requests select files and consume repository content.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Run the official server with least filesystem access and no deployment secrets.
- Constrain repository roots and request size.
- Keep lint findings advisory unless normal required CI independently verifies them.

## Verification

1. Attempt traversal, symlink escape, large requests, and malformed configuration.
2. Compare MCP results with pinned CI ESLint.
3. Audit requests without source leakage.

## Gotchas

- Agent tool output is not a required check.
- Plugins execute code.
- Editor and CI configurations can drift.

## Official source

- [Official documentation](https://eslint.org/docs/latest/use/mcp)
