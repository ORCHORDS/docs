# mcp-server-building

**Issue:** Building MCP servers requires understanding the protocol, transport options, and tool definition patterns
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A team wants to expose internal APIs as tools to AI agents via MCP. They are unsure how to structure tool definitions, handle authentication, implement the protocol correctly, and test the server before connecting it to an agent.

## Pattern / Solution
Use the official MCP SDK (Python: `mcp`, TypeScript: `@modelcontextprotocol/sdk`). Define tools with JSON Schema for inputs. Support stdio transport for local tools and HTTP/SSE for remote tools. Implement proper error handling — return structured errors, not unhandled exceptions. Add resource endpoints for data that agents should be able to read.

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server

server = Server("my-tool-server")

@server.tool()
async def search_documents(query: str, limit: int = 10) -> list[dict]:
    """Search internal documents by query. Returns list of matching document metadata."""
    return await db.search(query, limit=limit)

async def main():
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())
```

## Gotchas
- Tool descriptions are critical — the agent uses them for tool selection; be specific and include examples of when to use the tool
- Validate and sanitize all inputs — MCP tools can be invoked by agents with unexpected parameter combinations
- Return types must be JSON-serializable; complex objects need explicit serialization before returning

## Related
- mcp-client-patterns
- agent-tool-design
- llm-tool-use-patterns
