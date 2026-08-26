# MCP Inspector & MCP Server Debugging

> Debugging, testing, and validating MCP (Model Context Protocol) servers — the
> protocol that connects AI coding assistants (Cursor, Claude Code, Copilot, ZCode)
> to external tools and data sources. The de-facto integration standard in 2026.

---

## When to use this

- An MCP server connects in your IDE but its tools don't show up or fail on call.
- You're authoring a new MCP server and need to iterate on `tools/list`, `prompts/list`,
  or `resources/read` responses without round-tripping through a full agent.
- An agent reports "tool not found" or "invalid arguments" but your code looks correct.
- OAuth-secured remote MCP server returns 401/403 intermittently.

## Symptom

The agent can't see or call your tools, even though the server process is running
and no obvious error appears in the IDE.

```
Client → (stdio/SSE/HTTP) → MCP Server
  ↑ tools/list returns [] or tools/call returns error
```

The failure is silent because most clients swallow transport errors and just show
an empty tool list. The root cause lives in the server's JSON-RPC layer, not the
business logic.

## Step-by-step diagnosis

### 1. Launch the Inspector against your server

```bash
# stdio server (local script/binary)
npx @modelcontextprotocol/inspector node path/to/server/index.js

# remote HTTP/SSE server (2026 default — OAuth-secured)
npx @modelcontextprotocol/inspector --url https://my-server.example.com/mcp \
  --transport sse
```

The Inspector is transport-agnostic: it opens an interactive UI at
`http://localhost:6274` showing every protocol frame in both directions.

### 2. Check `initialize` handshake first

Before tools show up, the handshake must complete:
- Server returns `protocolVersion` the client understands
- `capabilities.tools` is present in the server response
- Client sends `initialized` notification

A missing `capabilities` field here = zero tools downstream, with no error.

### 3. Call `tools/list` manually

If the handshake succeeded but tools are empty:
- Verify your `ListToolsRequestSchema` handler returns `{ tools: [...] }`
  (not `{ tool: [...] }` — singular is the most common typo).
- Each tool needs `name`, `description`, and `inputSchema` (JSON Schema object).
- A malformed `inputSchema` (e.g. missing `type: "object"`) causes silent rejection.

### 4. Call `tools/call` with crafted arguments

Use the Inspector's form to invoke each tool with edge inputs:
- empty object `{}`
- missing required field
- extra unknown field (should the schema reject or ignore?)
- very long string (token budget exhaustion)
- unicode / emoji in string fields

This catches schema validation bugs that the agent would hit in production.

## Gotchas

- **Stdio buffering**: Node's `console.log` writes to stdout, which MCP uses as
  the transport. Any stray `console.log` corrupts the JSON-RPC stream and the
  client disconnects silently. Write logs to **stderr** (`console.error` or a
  pino logger pointing at fd 2) only.
- **Transport mismatch**: Connecting with `--transport stdio` to an SSE server
  (or vice versa) produces cryptic parse errors. Match the transport to what
  `server.connect()` actually set up.
- **OAuth token caching**: Remote servers cache bearer tokens per-session in the
  Inspector but not in CLI clients. A tool that works in the Inspector and fails
  from `claude mcp call` is usually a token-refresh bug, not a server bug.
- **Schema `$ref`**: Some clients (notably older Cursor builds) don't resolve
  `$ref` in `inputSchema`. Inline all definitions for maximum compatibility.
- **Long-running tools**: The default request timeout in many clients is 60s. A
  tool that indexes a repo or runs a build will be killed mid-flight. Implement
  progress notifications (`notifications/progress`) and raise the client timeout.
- **Inspector port conflict**: 6274 is hardcoded in some versions; if it's in
  use the Inspector exits with no message. `lsof -i :6274` before reporting a bug.
- **Protocol version drift**: Clients pin a specific `protocolVersion`. A server
  built against SDK 0.9 may negotiate down with a 1.x client and silently drop
  newer features (e.g. streaming tool output). Print the negotiated version.
- **`resources/list` empty ≠ broken**: Resources are optional. Many servers
  legitimately return `{ resources: [] }`. Don't chase this as a bug.

## Useful complementary tools

- **mcp-debugger** (github.com/debugmcp/mcp-debugger) — headless server that
  exposes step-through debugging as MCP tool calls, letting an agent itself
  set breakpoints.
- **MCPJam** — desktop GUI for batch-testing tools/prompts/resources.
- **MCP Debug Tools (VS Code)** — bridges the VS Code debugger to agents.

## See also

- `chrome-devtools-2026.md` — frontend debugging (orthogonal but often combined)
- `vscode-launch-json-debugging.md` — when your MCP server is also a Node app
