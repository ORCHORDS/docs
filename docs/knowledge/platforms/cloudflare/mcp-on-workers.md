# mcp-on-workers

**Issue:** Remote MCP server on Cloudflare Workers — the 2026 architecture
**Date:** 2026-08-09
**Repo:** example-org/example-repo at 196e96e
**Author:** the platform team
**Status:** verified-live (https://developers.cloudflare.com/agents/model-context-protocol/guides/remote-mcp-server/)

## Symptom

You build an MCP server. It works locally over stdio — Claude
Code calls your 5 tools, you're happy. Then you want to share
it: a teammate, another machine, Claude Desktop on a different
box. Stdio can't cross the network. You reach for HTTP+SSE,
discover it was deprecated in the 2025-03-26 spec, and land on
Streamable HTTP — but you don't know whether to keep a Durable
Object per session or run stateless, and OAuth looks like a
week of reading. You ship a half-working remote server and
debug it for a sprint.

## Root cause

**MCP transport + state is a 2D choice, not a 1D choice.**
Pick a transport (stdio, Streamable HTTP, RPC, SSE) and a
state model (stateless, McpAgent / Durable Object, raw SDK)
independently. Cloudflare's Agents SDK makes this explicit and
gives you 4 hand-tested combinations in 2026.

**Source:** Cloudflare Agents docs:
- Remote MCP server guide: https://developers.cloudflare.com/agents/model-context-protocol/guides/remote-mcp-server/
- Transport: https://developers.cloudflare.com/agents/model-context-protocol/protocol/transport/
- McpAgent API: https://developers.cloudflare.com/agents/model-context-protocol/apis/agent-api/
- Cloudflare MCP servers: https://developers.cloudflare.com/agents/model-context-protocol/cloudflare/servers-for-cloudflare/

**Source:** MCP spec:
- 2026-07-28 changelog: https://modelcontextprotocol.io/specification/2026-07-28/changelog
- 2026-07-28 release-candidate blog: https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/
- Streamable HTTP: https://modelcontextprotocol.io/specification/draft/basic/transports/streamable-http

**Source:** Cloudflare blogs:
- "Remote Model Context Protocol servers": https://blog.cloudflare.com/remote-model-context-protocol-servers-mcp/
- "The next generation of MCP" (MCP 2026-07-28 support): https://blog.cloudflare.com/mcp-v2/
- "MCP, authn & Durable Objects free tier": https://blog.cloudflare.com/building-ai-agents-with-mcp-authn-authz-and-durable-objects/

## The "MCP on Workers" concept

MCP on Cloudflare Workers is a first-class deployment
target. The Agents SDK provides 4 server shapes and 4
transport shapes. The combination is your call.

- **Server shapes:** `createMcpHandler` (stateless), `createLegacyMcpHandler` (legacy compatibility), `McpAgent` (stateful, deprecated for new code), raw SDK (custom).
- **Transport shapes:** stdio (local only), Streamable HTTP (standard remote, since 2025-03-26), RPC (Cloudflare-internal only), SSE (legacy, deprecated under 2026-07-28).
- **Endpoint convention:** `/mcp` is the new standard. `/sse` remains as an alias to the same Streamable HTTP handler for backward compatibility but no longer serves the deprecated HTTP+SSE transport.
- **Spec:** Cloudflare's own servers support the new MCP 2026-07-28 Specification as of July 28, 2026; `/mcp` accepts stateless requests from 2025 Streamable HTTP clients. (Changelog: https://developers.cloudflare.com/changelog/post/2026-07-28-cloudflare-mcp-servers-mcp-2026-07-28/)

The pattern is: pick stateless unless you need state.

## The "createMcpHandler (stateless)" pattern

For a stateless remote MCP server with no per-session state:

```ts
// src/index.ts
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { createMcpHandler } from 'agents/mcp';
import { z } from 'zod';

const server = new McpServer({ name: 'Demo', version: '1.0.0' });
server.tool(
  'add',
  'Add two numbers',
  { a: z.number(), b: z.number() },
  async ({ a, b }) => ({ content: [{ type: 'text', text: String(a + b) }] })
);

export default createMcpHandler(server);
```

No Durable Object binding. No migration. Deploys in one
`wrangler deploy`. Best for tools that don't need memory.

## The "McpAgent (stateful)" pattern

For a stateful remote MCP server — per-session persistence,
embedded SQL, WebSocket hibernation:

```ts
import { McpAgent } from 'agents/mcp';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';

export class MyMCP extends McpAgent<Env, State> {
  server = new McpServer({ name: 'Demo', version: '1.0.0' });
  initialState: State = { counter: 0 };

  async init() {
    this.server.tool(
      'add',
      'Increment the persisted counter',
      { n: z.number() },
      async ({ n }) => {
        this.setState({ counter: this.state.counter + n });
        return { content: [{ type: 'text', text: String(this.state.counter) }] };
      }
    );
  }
}

export default MyMCP.serve('/mcp');
```

`wrangler.jsonc`:
```jsonc
{
  "durable_objects": { "bindings": [{ "name": "MCP_OBJECT", "class_name": "MyMCP" }] },
  "migrations": [{ "new_sqlite_classes": ["MyMCP"], "tag": "v1" }]
}
```

Each client session = one Durable Object + one SQLite DB. Idle
sessions hibernate (no compute). Required on first deploy.

## The "OAuth with workers-oauth-provider" pattern

For an authenticated remote MCP server:

```ts
import { OAuthProvider } from '@cloudflare/workers-oauth-provider';
import { MyMCP } from './mcp-agent';

export default new OAuthProvider({
  apiHandlers: { '/mcp': MyMCP.serve('/mcp') },
  authorizeEndpoint: '/authorize',
  tokenEndpoint: '/token',
  clientRegistrationEndpoint: '/register',
  defaultHandler: GitHubHandler, // or Google, Access, Auth0, WorkOS, or your own
});
```

Four auth patterns supported:
- **Cloudflare Access** as the IdP (enterprise SSO).
- **Third-party** (GitHub, Google) — Worker issues bound token after external consent.
- **Auth-as-a-service** (Stytch, Auth0, WorkOS).
- **Custom** — Worker handles the full flow.

OAuth 2.1 + PKCE. The provider wraps the OAuth dance so you
don't hand-roll the protocol.

**Source:** https://blog.cloudflare.com/building-ai-agents-with-mcp-authn-authz-and-durable-objects/

## The "Streamable HTTP" pattern (the 2025-03-26 + 2026-07-28 spec)

For external MCP servers, production apps — use Streamable
HTTP, not the deprecated HTTP+SSE.

```
POST /mcp   (tool calls, list, anything)
GET  /mcp   (legacy SSE stream — REMOVED under 2026-07-28)
```

**2026-07-28 changes (finalized 2026-07-28):**
- Protocol-level sessions and the `Mcp-Session-Id` header are gone (SEP-2567).
- The `initialize`/`initialized` handshake is gone (SEP-2575). Protocol version and capabilities travel in `_meta` on every request.
- `Mcp-Method` and `Mcp-Name` headers are **REQUIRED** on every Streamable HTTP request (SEP-2243), so load balancers and gateways can route without inspecting the body.
- List endpoints no longer vary per connection; add `ttlMs` and `cacheScope` to enable HTTP-cache-style behavior (SEP-2549).
- HTTP+SSE transport is deprecated (SEP-2596) — migrate to Streamable HTTP.
- W3C Trace Context propagation in `_meta` is now documented (SEP-414) — `traceparent`, `tracestate`, `baggage` keys.

**Source:** https://modelcontextprotocol.io/specification/2026-07-28/changelog

## The "RPC transport (internal only)" pattern

For internal agents on Cloudflare — both server and agent in
the same Worker. JSON-RPC over Cloudflare's RPC bindings, no
HTTP, no auth required.

```ts
import { Agent } from 'agents';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';

class ChatAgent extends Agent {
  async onStart() {
    this.mcp = await this.mcp.connect('http://localhost/my-mcp');
  }
}
```

**Use when:** server and agent are both in CF, latency matters,
no external clients.
**Don't use when:** you need auth or external clients.

## The "endpoints" pattern (URLs that matter)

| Endpoint | Status | When |
|---|---|---|
| `/mcp` | **Standard** (2026+) | New connections; 2026-07-28 stateless + 2025 Streamable HTTP both served |
| `/sse` | Alias (backward compat) | Same Streamable HTTP handler, but does NOT serve deprecated HTTP+SSE |
| `/sse` as HTTP+SSE | Deprecated | Use Streamable HTTP or auto-detect |
| Local stdio | Local only | Claude Code + Claude Desktop direct |

`serveSSE("/sse")` requires the **client URL match exactly** —
`https://worker.dev/sse`, not `https://worker.dev`. The base
path is prepended to all MCP endpoints automatically.

## The "jurisdiction" pattern (data residency)

For EU or FedRAMP compliance:

```ts
export class MyMCP extends McpAgent<Env, State> {
  // ... tool defs
}
export default MyMCP.serve('/mcp', { jurisdiction: 'eu' });
// or 'fedramp'
```

All session data, tool state, and Durable Object storage stays
in the specified jurisdiction.

## The "KV eventual-consistency gotcha" pattern

When using `workers-oauth-provider` with **dynamic client
registration**, the KV-backed client store is eventually
consistent. A client that just registered may get a 401 for
up to 60s on the first token exchange. Either:
- Use the D1-backed client store (not KV), or
- Document the 60s warm-up window, or
- Pre-register the client during deployment.

**Source:** https://docs.mcpmanager.ai/build-your-own-mcp-server/cloudflare

## The "tool result format" pattern (CRITICAL)

All MCP tool results MUST return this exact shape:

```ts
{
  content: [{ type: 'text', text: '...your result as string...' }]
}
```

If you return a raw object, the client sees `[object Object]`.
Stringify, or wrap in `{ type: 'text', text: JSON.stringify(obj) }`.

## The "AI Playground as a remote MCP client" pattern

The Cloudflare AI Playground is a fully remote MCP client —
enter a server URL, click Connect, you get OAuth if it's set
up. It's the fastest way to test your remote server without
installing a client.

**URL:** https://playground.ai.cloudflare.com/

## The "mcp-remote proxy" pattern (legacy client fallback)

Some clients (notably older Claude Desktop) only support stdio.
To connect them to a remote server, use `mcp-remote`:

```json
{
  "mcpServers": {
    "my-remote": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://my-mcp.worker.dev/mcp"]
    }
  }
}
```

`mcp-remote` is a local proxy that does the Streamable HTTP
dance on the client's behalf.

## The "local testing with MCP Inspector" pattern

```bash
# Run the inspector
npx @modelcontextprotocol/inspector

# Open http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=...
# Transport: Streamable HTTP
# URL: http://localhost:8787/mcp
# Click Connect → List Tools → invoke
```

The inspector lets you invoke any tool from the browser. Use
it before connecting a real client.

## The "Cloudflare's own MCP servers" pattern

Cloudflare runs its own product-specific MCP servers over
Streamable HTTP at `/mcp`:

| Server | URL | Tools |
|---|---|---|
| Cloudflare API | `https://api.mcp.cloudflare.com/mcp` | ~2,500 endpoints (DNS, Workers, R2, Zero Trust, …) wrapped in 2 meta-tools |
| Documentation | `https://docs.mcp.cloudflare.com/mcp` | Search + fetch Cloudflare docs |
| Workers Bindings | `https://bindings.mcp.cloudflare.com/mcp` | Build Workers with storage, AI, compute primitives |
| Workers Builds | `https://builds.mcp.cloudflare.com/mcp` | Cloudflare Workers Builds insights |

These are the reference implementations — read their tool
schemas for the canonical MCP tool-result format.

## The "remote MCP anti-patterns" anti-patterns

### 1. Returning raw objects from tools
- **Issue:** Client sees `[object Object]`
- **Fix:** Always `{ content: [{ type: 'text', text: '...' }] }`

### 2. Stateful server when stateless suffices
- **Issue:** Durable Object cost + complexity for nothing
- **Fix:** Default to `createMcpHandler`; reach for `McpAgent` only if you need `setState` / `sql`

### 3. Forgetting the `migrations` block on first deploy
- **Issue:** `new_sqlite_classes` migration missing → DO fails to instantiate
- **Fix:** Always include the `migrations` array when adding a Durable Object class

### 4. Mixing `/sse` (HTTP+SSE) and `/mcp` (Streamable HTTP) endpoints
- **Issue:** 2026-07-28 deprecates HTTP+SSE; legacy clients fail
- **Fix:** Serve both from the same Streamable HTTP handler; tell clients to use `/mcp`

### 5. Custom bearer auth instead of OAuth
- **Issue:** Most MCP clients assume OAuth; bearer breaks Claude Desktop auto-discovery
- **Fix:** Use `workers-oauth-provider` with GitHub/Google/Access/Auth0

### 6. No `Mcp-Method` / `Mcp-Name` headers (pre-2026-07-28 server)
- **Issue:** New clients (post-July 2026) reject the request
- **Fix:** Upgrade to the latest Agents SDK + MCP TypeScript SDK; the headers are set automatically

### 7. KV-backed client store + dynamic registration
- **Issue:** 60s post-registration 401s
- **Fix:** Pre-register clients, or use D1

## The "remote MCP checklist" pattern

For a production remote MCP server:
- [ ] Server shape matches state needs (stateless vs `McpAgent`)
- [ ] `wrangler.jsonc` has Durable Object binding + migration
- [ ] Endpoint is `/mcp` (not `/sse` for new code)
- [ ] OAuth via `workers-oauth-provider` (not custom bearer)
- [ ] All tool results return `{ content: [{ type: 'text', text: '...' }] }`
- [ ] Jurisdiction set if data-residency required (`eu` / `fedramp`)
- [ ] W3C Trace Context propagated via `_meta` if observability matters
- [ ] Test with MCP Inspector before connecting real clients
- [ ] `mcp-remote` fallback for legacy stdio-only clients
- [ ] Cloudflare changelog tracked: 2026-07-28 spec is final

## Verification
- **Test:** `npx wrangler deploy` → `curl https://my-mcp.worker.dev/mcp` returns the tools manifest
- **Test:** MCP Inspector connects, lists tools, invokes one
- **Test:** OAuth round-trip: `mcp-remote https://my-mcp.worker.dev/mcp` works in Claude Desktop
- **Live:** AI Playground connects to `https://my-mcp.worker.dev/mcp` and invokes a tool
- **Audit:** Re-read Cloudflare changelog quarterly (2026-07-28 is the current spec; next bump in ~6-9 months)

## Gotchas
- **The "raw object return" anti-pattern.** Always `{ content: [{ type: 'text', text: '...' }] }`.
- **The "missing migration" anti-pattern.** First deploy of a new DO class MUST have `migrations`.
- **The "KV + DCR" gotcha.** KV is eventually consistent; 60s post-registration 401s are normal.
- **The "/sse vs /mcp" gotcha.** 2026-07-28 deprecates the HTTP+SSE transport; old clients must switch to Streamable HTTP.
- **The "base path" gotcha.** `serveSSE("/sse")` requires the client URL to end in `/sse` exactly.

## Related
- `cloudflare/agents-sdk-best-practices.md` — broader Agents SDK patterns
- `cloudflare/durable-objects-best-practices.md` — DO bindings, hibernation
- `cloudflare/durable-objects-patterns.md` — stateful patterns
- `cloudflare/ai-gateway-best-practices.md` — if your MCP server proxies to a model
- `patterns/mcp-server-patterns.md` — generic MCP server design (cross-platform)
- `security/oauth-best-practices.md` — OAuth 2.1 + PKCE details
- `security/owasp-api-top-10-2023.md` — if your MCP server exposes business data

**Source URLs (verified 2026-08-09):**
- Cloudflare: https://developers.cloudflare.com/agents/model-context-protocol/guides/remote-mcp-server/
- Cloudflare transport: https://developers.cloudflare.com/agents/model-context-protocol/protocol/transport/
- Cloudflare McpAgent: https://developers.cloudflare.com/agents/model-context-protocol/apis/agent-api/
- Cloudflare MCP servers: https://developers.cloudflare.com/agents/model-context-protocol/cloudflare/servers-for-cloudflare/
- Cloudflare changelog (2026-07-28): https://developers.cloudflare.com/changelog/post/2026-07-28-cloudflare-mcp-servers-mcp-2026-07-28/
- Cloudflare blog: https://blog.cloudflare.com/remote-model-context-protocol-servers-mcp/
- Cloudflare blog (MCP v2): https://blog.cloudflare.com/mcp-v2/
- Cloudflare blog (auth + DO): https://blog.cloudflare.com/building-ai-agents-with-mcp-authn-authz-and-durable-objects/
- MCP 2026-07-28 spec changelog: https://modelcontextprotocol.io/specification/2026-07-28/changelog
- MCP 2026-07-28 RC blog: https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/
- MCP Streamable HTTP: https://modelcontextprotocol.io/specification/draft/basic/transports/streamable-http
- MCP spec timeline: https://hidekazu-konishi.com/entry/mcp_specification_version_timeline.html
- MCP Manager on CF: https://docs.mcpmanager.ai/build-your-own-mcp-server/cloudflare
- Cloudflare AI Playground: https://playground.ai.cloudflare.com/
- mcp-remote: https://www.npmjs.com/package/mcp-remote
- MCP Inspector: https://github.com/modelcontextprotocol/inspector
- The shipped `packages/mcp-server/` in this repo: the local stdio equivalent
- The stub `packages/claude-desktop-mcp/`: the planned Claude Desktop chat-app integration
