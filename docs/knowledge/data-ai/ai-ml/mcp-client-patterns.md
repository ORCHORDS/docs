# mcp-client-patterns

**Issue:** Connecting AI agents to MCP servers requires proper client initialization, tool discovery, and error handling
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
An agent framework needs to dynamically discover and invoke tools from multiple MCP servers. Tool invocations fail silently, discovery is slow, and there is no graceful handling of server disconnection mid-session.

## Pattern / Solution
Initialize MCP clients at agent startup, not per-request. Cache tool listings and refresh periodically or on reconnection. Implement reconnection logic for stdio servers. Handle tool call errors explicitly — distinguish between tool-not-found, invalid-params, and tool-execution-error. Multiplex multiple servers and present a unified tool namespace to the agent.

```python
from mcp import ClientSession
from mcp.client.stdio import stdio_client

async def connect_mcp_server(command: list[str]):
    async with stdio_client(command) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            tools = await session.list_tools()
            return session, tools
```

## Gotchas
- MCP server processes die if the parent process closes the stdio pipe — manage server lifecycle explicitly
- Tool schemas can change between server restarts — re-discover tools on reconnection rather than using stale cache
- Large tool lists slow down LLM context — filter to relevant tools per task rather than sending all available tools

## Related
- mcp-server-building
- agent-tool-design
- llm-tool-use-patterns
- agent-architecture-patterns
