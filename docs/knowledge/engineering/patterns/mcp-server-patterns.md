# mcp-server-patterns

**Issue:** MCP server design patterns — cross-platform, 2026
**Date:** 2026-08-09
**Repo:** example-org/example-repo at 196e96e
**Author:** the platform team
**Status:** verified-live (https://modelcontextprotocol.io/specification/2026-07-28/server/tools)

## Symptom

You build an MCP server. It exposes 40 tools — every API
endpoint mirrored 1:1. Descriptions are 2 paragraphs each. The
agent picks the wrong tool 30% of the time. The first time
the upstream API is slow, the server goes down for an hour.
A token leaks in a tool result. A user can read another
user's data because the resource URI didn't validate the
tenant. You spend 3 months hardening what should have been
designed right the first time.

## Root cause

**MCP is not "expose your API as tools."** It's a
model-facing interface that has to be designed around what
the model is good at (structured, narrow, idempotent) and
bad at (broad, ambiguous, destructive without guardrails).
The 2026-07-28 spec, the OAuth 2.1 + PKCE mandate, the
JSON Schema 2020-12 changes, and the rate-limit / circuit-breaker
requirements make 2024-era patterns obsolete.

**Source:** MCP spec:
- Tools: https://modelcontextprotocol.io/specification/2026-07-28/server/tools
- 2026-07-28 changelog: https://modelcontextprotocol.io/specification/2026-07-28/changelog
- 2026-07-28 blog: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- SEP-2106 (JSON Schema 2020-12): https://modelcontextprotocol.io/seps/2106-json-schema-2020-12

**Source:** Industry guides:
- MCP Tool Schema Design Guide 2026: https://kansei-link.com/en/insights/mcp-tool-schema-design-guide-2026.html
- MCP Schema Design (yaw): https://yaw.sh/mcp-in-production/mcp-schema-design/
- 12 Rules for Production: https://apigene.ai/blog/mcp-best-practices
- AWS MCP Tool Design: https://aws.amazon.com/blogs/machine-learning/mcp-tool-design-practical-approaches-and-tradeoffs/
- MCP Rate Limiting Implementation: https://kansei-link.com/en/insights/mcp-rate-limiting-implementation-guide-2026
- arxiv — MCP Server Architecture Patterns: https://arxiv.org/abs/2606.30317
- cyanheads MCP dev guide: https://github.com/cyanheads/model-context-protocol-resources/blob/main/guides/mcp-server-development-guide.md

## The "five architecture patterns" concept

Industry survey of 15 production MCP servers (arxiv
2606.30317) catalogues five recurring shapes:

1. **Resource Gateway** — server fronts a data source (DB, S3, API) and exposes Resources. Read-mostly. Stateless. Typical: docs server, file indexer.
2. **Tool Orchestrator** — server coordinates multiple other MCP servers or APIs to fulfill a workflow. Stateful (caches the plan). Typical: "research and summarize" agent.
3. **Stateful Session Server** — `McpAgent` on Cloudflare, or a long-lived backend process. Per-session memory, embedded SQL, WebSocket hibernation. Typical: chat app with persistent context.
4. **Proxy Aggregator** — server fans out to N backends (Claude, OpenAI, local), translates between them, returns one normalized shape. Typical: model-routing router.
5. **Domain-Specific Adapter** — narrow adapter for one product (Stripe, GitHub, Salesforce). Stateless. Ships 5-20 focused tools, not the entire upstream API.

The shape you pick determines the transport (stdio vs
Streamable HTTP), state model (stateless vs DO), and which
cross-cutting concerns (auth, rate limit, observability)
matter.

## The "tool naming" pattern

For every tool:
- **snake_case or camelCase** — pick one, stay consistent.
- **verb + object** — `create_invoice`, `search_docs`, `list_users`. Never just `invoices` (noun only — model has to infer action).
- **1-128 characters** (spec).
- **Domain-named**, not backend-named. `customer_search` not `sql_select_with_join`.

```
✅ create_invoice, search_docs, list_open_issues
❌ invoices, docs, query
```

## The "tool description" pattern

A description must answer four questions in 200-400 characters:

1. **What** it does (action)
2. **When** to use it (input prerequisite — auth scope, state, etc.)
3. **What** comes back (output expectation — types, limits)
4. **Why this one** (vs. similar alternatives)

```ts
server.tool(
  'create_invoice',
  'Create a new invoice in the customer\'s account. Requires `invoices:create` scope. ' +
  'Returns the created invoice with its server-assigned id and `status: "draft"`. ' +
  'Use this when the user wants to bill a customer; for batch operations, use `create_invoice_batch`.',
  { customer_id: z.string().uuid(), lines: z.array(...) },
  async (args) => { ... }
);
```

The description is the API contract. Verbose marketing copy
is the #1 token-waste driver.

## The "inputSchema as flat as possible" pattern

Deep nesting hurts model selection. Two options when a
complex object looks necessary:

- **Decompose** — expand nested objects to top-level arguments.
- **Split** — three specific tools > one generic tool.

```ts
// ❌ nested
{ customer: { id: z.string(), address: { city, country } }, lines: [...] }

// ✅ flat
{ customer_id: z.string(), city: z.string(), country: z.string(), lines: z.array(...) }
```

JSON Schema 2020-12 is allowed in `inputSchema` since
SEP-2106 (`oneOf`, `anyOf`, `$ref`, conditionals), so use it
sparingly — only when flat decomposition loses meaning.

## The "annotations (untrusted hints)" pattern

Every tool can carry 5 annotations (2025-03-26 spec):

| Field | Meaning | Default |
|---|---|---|
| `title` | Human-readable display name | none |
| `readOnlyHint` | Modifies no state | `false` |
| `destructiveHint` | May delete/overwrite (only if not readOnly) | `true` |
| `idempotentHint` | Repeated calls = same result (only if not readOnly) | `false` |
| `openWorldHint` | Interacts with external services (internet, third-party APIs) | `true` |

**Critical security rule:** clients **MUST NOT** rely on
annotations for security decisions. They are hints from an
untrusted server. Your server should validate inputs and
enforce scopes regardless of what the client says the
annotations are.

## The "workflow tools > raw endpoints" pattern

Build tools that complete a user task, not tools that mirror
every API endpoint. Workflow tools:

- Reduce multi-step planning errors
- Give you a single place to enforce preconditions
- Make partial-failure handling tractable

```ts
// ❌ raw API mirror (6 calls to do "buy a product")
add_to_cart, get_shipping_options, set_shipping_address,
calculate_tax, create_payment_intent, confirm_payment

// ✅ workflow tool (1 call)
buy_product({ product_id, address, payment_method })
```

Trade-off: less flexible. Some clients want raw endpoints.
Solution: ship both, mark the workflow as primary in
description, expose raw endpoints for power users.

## The "surface reduction" pattern

Three patterns reduce tool count without losing power:

1. **Profile-based loading** — start the server with `--profile=read-only` or `--profile=ec2` to expose a subset.
2. **Split the server** — `@yawlabs/aws-ec2-mcp` + `@yawlabs/aws-s3-mcp` beats one mega-server. Clients load only what they need.
3. **Collapse synonyms** — three "start workflow" tools with slight variations → one tool with an enum parameter.

The "Six-Tool Pattern" (MCP Bundles): three reads, two
writes, one admin. Default to fewer tools; add only when
the model proves it needs them.

## The "idempotency by default" pattern

Every write tool should be idempotent:

- Accept an `idempotency_key` parameter (let the client provide a UUID, dedupe on it)
- OR use natural keys (an email, a slug) that the second call would dedupe on
- OR return the same result for the same input (and let the client detect "already done" from the response)

Without this, network retries create duplicates.

## The "input validation at boundaries" pattern

Declaring JSON Schema is not enough. The server must also
validate at the code boundary, because:

- Agents sometimes call tools ignoring the schema
- Malicious users can send unsafe input through a trusted agent

Mandatory validation checklist:
- **Types and required fields** — enforce per JSON Schema
- **Length and range** — `string.max_length`, numeric `min`/`max`
- **File paths / commands / URLs** — sanitize against injection (path traversal, command injection, SSRF)
- **Auth scope** — verify the tool can be called with the caller's scope
- **Rate limit** — token-bucket gate before hitting upstream

Centralize: one input model per tool (Zod in TS, Pydantic in Python). Reuse in the handler, in tests, in docs.

## The "OAuth 2.1 + PKCE + Resource Indicators" pattern

The 2026-04 spec update made these mandatory for public
remote MCP servers:

- **OAuth 2.1** with **PKCE** (no implicit flow — it's removed).
- **RFC 8707 Resource Indicators** — embed the target MCP server URI in the access token's `audience` claim. Prevents a leaked token from being reused against other services.
- **Client credentials grant** for machine-to-machine (autonomous agents without a human in the loop).
- **15-60 min access token expiry.** Rotate refresh tokens on each use. Atomic lock (Redis SETNX) when multiple agent instances share credentials.
- **Tool-level scopes** — `invoices:read`, `invoices:create`, `reports:export`. Finer-grained scopes limit blast radius of a compromised agent session.

Authorization server support: Keycloak 18+, Auth0 Enterprise,
and the `workers-oauth-provider` library (Cloudflare). For
custom: add `resource` parameter to token endpoint, embed
MCP server URI in `audience` claim.

The 2026-07-28 spec also adds (SEP-2468): the authorization
server should return the `iss` parameter per RFC 9207, and
clients MUST validate it before redeeming a code. Closes an
authorization-server mix-up attack.

## The "two-layer rate limiting" pattern

Run rate limits at two layers:

| Layer | Scope | Example limit |
|---|---|---|
| **Per-client** | Total requests per client ID / API key | 100 req/min, 2000 req/hour |
| **Per-tool** | Destructive ops stricter; reads looser | `delete_invoice`: 5/min; `list_invoices`: 100/min |

Implement with atomic counters (Postgres `UPDATE ... RETURNING`, Redis `INCR + EXPIRE`). In-memory doesn't survive multi-instance.

When exceeded:
- **HTTP transport:** return `429 Too Many Requests` with `Retry-After: <seconds>` header
- **stdio / JSON-RPC:** embed `retry_after_seconds` and `scope` in `error.data`

Combine with **circuit breaker** per upstream dependency:
Closed (normal) → Open (tripped after 50% error rate over
1 min) → Half-Open (probe after 30s cooldown). Prevents pile-up
during upstream outages.

## The "error handling" pattern (3-category taxonomy)

Return tool errors **in-band** (`isError: true` in the
result), **not as JSON-RPC protocol errors**. The JSON-RPC
error field is for protocol-level failures, not tool logic.
The agent needs structured, recoverable errors.

| Category | HTTP | Retry? | Required fields |
|---|---|---|---|
| **CLIENT_ERROR** (4xx) | 400, 401, 403, 404 | No | `error_type`, `message` (what's wrong + how to fix), `field_errors` (per-field) |
| **SERVER_ERROR** (5xx) | 500, 503 | Yes | `error_type`, `message`, `retry_recommended: true`, `retry_after_seconds`, `correlation_id` |
| **EXTERNAL_ERROR** (502, 503) | Upstream down | Maybe | `error_type`, `dependency` (name), `message` (suggest fallback), `retry_recommended: true` |

```json
{
  "isError": true,
  "content": [{ "type": "text", "text": "..." }],
  "error_type": "validation_error",
  "message": "invoice_date must be ISO 8601 (YYYY-MM-DD). Received: 'April 14, 2026'.",
  "field_errors": { "invoice_date": "expected YYYY-MM-DD" },
  "retry_recommended": false,
  "correlation_id": "req_abc123"
}
```

**Exponential backoff with jitter** for retries. Never fixed
interval — synchronized retries amplify outages.

## The "versioning" pattern

MCP servers evolve. Tool names change, parameters get added,
response formats shift. Without versioning, a server update
breaks every agent that connects.

- **Pin to specific server versions** in production
- **Test new versions in staging** before deploying
- **Maintain backwards compatibility** for at least one version (deprecate, don't remove)
- **Document breaking changes** in a CHANGELOG the agent can read at startup

In `tools/list` response, include `serverInfo.version`. The
agent can decide whether to upgrade.

## The "health check" pattern

MCP servers can fail silently — connection stays open, server
stops responding, or returns malformed results the agent
parses as valid.

Health check should verify:
- The server process is running
- A representative tool call returns the expected response shape
- Latency is within bounds
- Auth tokens haven't expired (don't make the first user request the canary)

Expose as a plain `health_check` tool (or HTTP endpoint for
remote servers). Run every 30s from the monitoring layer.

## The "result format" pattern (3 things to know)

The 2026-07-28 spec lets tool results include **structured
content** alongside the text content. Both are valid; both
should be set when an `outputSchema` is declared:

```json
{
  "content": [{ "type": "text", "text": "Invoice 123 created, total $450" }],
  "structuredContent": {
    "id": "inv_123",
    "total": 45000,
    "currency": "USD",
    "status": "draft"
  }
}
```

Three rules:
1. **Always set `content[0].text`** for human/log readability — even if `structuredContent` carries the data
2. **Validate `structuredContent` against `outputSchema`** if declared
3. **Don't inline megabytes** — return handles/URIs to large resources, not the full payload

`outputSchema` validation (since SEP-2106): `outputSchema` is
now any valid JSON Schema 2020-12 (no `type: "object"` root
constraint). Servers MUST conform; clients SHOULD validate.

## The "MCP server is infrastructure" pattern

Treat the MCP server like production infrastructure, not a
script. The 12 rules (paraphrased from apigene):

1. Start with the verb in tool names
2. Include parameter constraints in descriptions
3. Use dynamic tool loading (profile-based, lazy)
4. Secrets via env vars / secrets manager, never in config files
5. Per-tool access control (read / write / execute by role)
6. Log every tool call (tool name, inputs redacted, latency, caller identity)
7. Structured error responses (the 3-category taxonomy above)
8. Version the server, deprecate not remove
9. Health checks every 30s
10. Streamable HTTP for remote (not the deprecated HTTP+SSE)
11. Separate dev / staging / production server configs
12. Run in containers with restricted network egress

## The "2026-07-28 spec changes" pattern

The current MCP spec (final 2026-07-28) changes that matter
for server authors:

- **Mcp-Method + Mcp-Name headers REQUIRED on Streamable HTTP** (SEP-2243) — your gateway/WAF/rate-limiter can route and meter on these headers, not by parsing the JSON body
- **JSON-RPC error `-32002` (resource not found) → `-32602` (Invalid Params)** (SEP-2164) — align with JSON-RPC standard
- **OAuth `iss` per RFC 9207** (SEP-2468) — clients validate before redeeming code
- **`application_type` in Dynamic Client Registration** (SEP-837) — fixes localhost redirects for desktop/CLI
- **Client credentials bound to issuer** (SEP-2352) — no reuse across authorization servers
- **DCR formally deprecated in favor of CIMD** (Client ID Metadata Documents) — DCR still works for backward compat
- **Full JSON Schema 2020-12** in `inputSchema` and `outputSchema` (SEP-2106) — compositions + refs
- **Protocol-level sessions and `Mcp-Session-Id` removed** (SEP-2567) — servers mint explicit handles
- **`initialize`/`initialized` handshake removed** (SEP-2575) — protocol version + capabilities travel in `_meta`
- **Three features deprecated** (SEP-2577) under formal lifecycle: Roots → tool params; Sampling → direct LLM API; Logging → stderr or OpenTelemetry. Methods continue to work for ≥ 12 months.

## The "security gotchas" pattern

The 5 most-exploited categories:

1. **Path traversal in resource URIs** — `db://path/to/etc/passwd`. Sanitize and normalize every path. Resolve to absolute, then verify it stays inside the allowlist.
2. **Prompt injection via tool results** — if your tool returns user-controlled content (forum post, file content), the model can be tricked into calling other tools with attacker payloads. Strip or sandbox.
3. **Secrets in tool results** — return only the last 4 of a credit card, mask emails in exports. Redact by default.
4. **Trusting annotations** — they're server-supplied hints. Never use `readOnlyHint` to skip authorization. Always re-validate scope.
5. **Dependency vulnerabilities** — `npm audit` / `pip audit` in CI. Pin to lockfile. Update monthly.

## The "MCP server checklist" pattern

For a production MCP server:
- [ ] Tool names: snake_case (or camelCase), verb + object
- [ ] Descriptions: 200-400 chars, action + prerequisite + output + when to pick
- [ ] `inputSchema`: as flat as possible; JSON Schema 2020-12 inside `type: "object"`
- [ ] `outputSchema` declared when structured result
- [ ] All 5 annotations explicitly set on every tool
- [ ] In-band errors with `isError: true` + 3-category taxonomy
- [ ] `structuredContent` + `content[0].text` both set
- [ ] Large payloads return Resource URIs, not inline
- [ ] OAuth 2.1 + PKCE + Resource Indicators (RFC 8707) for remote
- [ ] Access token expiry ≤ 60 min; refresh token rotation
- [ ] Tool-level scopes validated per request
- [ ] Two-layer rate limits (per-client + per-tool)
- [ ] HTTP 429 + `Retry-After` for HTTP; `retry_after_seconds` in stdio errors
- [ ] Circuit breaker per upstream dependency
- [ ] Exponential backoff with jitter on retries
- [ ] Idempotency key on every write tool
- [ ] Health check tool + monitoring integration
- [ ] Server version in `tools/list` response
- [ ] Streamable HTTP for remote (not HTTP+SSE)
- [ ] Mcp-Method + Mcp-Name headers set (SEP-2243)
- [ ] Tool tokens < 3K for 10 tools, < 20K per server
- [ ] Path/command/URL sanitization
- [ ] Secrets via env vars / vault, never in config
- [ ] Deprecation not removal; CHANGELOG
- [ ] Per-tool access control (read/write/execute)
- [ ] Log every call with caller identity
- [ ] MCP Inspector tested before deploy

## Verification
- **Test:** `npx @modelcontextprotocol/inspector` connects, lists tools, invokes one
- **Test:** OAuth round-trip via `mcp-remote` or AI Playground
- **Test:** Schema validation: missing field, wrong type, path traversal, SQL injection — all return `CLIENT_ERROR`, never reach upstream
- **Test:** Rate limit: 100+ requests in 1 min → 429 with `Retry-After`
- **Test:** Circuit breaker: upstream timeout → server rejects for 30s, no pile-up
- **Test:** 3-category error coverage (force each, verify response shape)
- **Audit:** Re-read MCP changelog quarterly (2026-07-28 is current; next bump in ~6-9 months)

## Gotchas
- **The "annotations are trusted" anti-pattern.** They're server-supplied hints. Re-validate scope.
- **The "raw object return" anti-pattern.** Always `content: [{ type: 'text', text: '...' }]` + optional `structuredContent`.
- **The "40 tools mirroring the API" anti-pattern.** Workflow tools, not endpoint mirrors.
- **The "deeply nested inputSchema" anti-pattern.** Decompose or split.
- **The "implicit flow OAuth" anti-pattern.** Removed from MCP spec; use authorization code + PKCE.
- **The "fixed-interval retries" anti-pattern.** Exponential backoff with jitter, always.
- **The "in-memory rate limit" anti-pattern.** Multi-instance breaks it; use atomic counter.
- **The "no idempotency" anti-pattern.** Every write tool needs a dedupe key.
- **The "DCR for new clients" anti-pattern.** Use CIMD (SEP-837); DCR is deprecated.
- **The "secret in tool result" anti-pattern.** Mask by default; redact PII.

## Related
- `cloudflare/mcp-on-workers.md` — the CF-specific sibling (this entry is cross-platform)
- `security/oauth-best-practices.md` — OAuth 2.1 + PKCE + Resource Indicators deep-dive
- `patterns/idempotency-keys.md` — idempotency design
- `patterns/retry-with-exponential-backoff.md` — backoff with jitter
- `patterns/circuit-breaker-pattern.md` — circuit breaker states
- `patterns/api-rate-limit-by-key.md` — per-key rate limiting
- `patterns/api-rate-limiting-detail.md` — full rate-limiting math
- `patterns/api-design-best-practices.md` — broader API design
- `patterns/api-design-anti-patterns.md` — anti-patterns to avoid
- `patterns/feature-cookbook-pagination.md` — pagination for large results
- `security/owasp-api-top-10-2023.md` — OWASP API risks
- `security/log-injection-prevention.md` — for tool results that include user content
- The shipped `packages/mcp-server/` in this repo — local stdio example
- The stub `packages/claude-desktop-mcp/` — the planned chat-app integration

**Source URLs (verified 2026-08-09):**
- MCP spec tools: https://modelcontextprotocol.io/specification/2026-07-28/server/tools
- MCP 2026-07-28 changelog: https://modelcontextprotocol.io/specification/2026-07-28/changelog
- MCP 2026-07-28 blog: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- MCP 2026-07-28 release candidate: https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/
- SEP-2106 (JSON Schema 2020-12): https://modelcontextprotocol.io/seps/2106-json-schema-2020-12
- MCP best practices (apigene): https://apigene.ai/blog/mcp-best-practices
- MCP Tool Schema Design Guide 2026 (kansei-link): https://kansei-link.com/en/insights/mcp-tool-schema-design-guide-2026.html
- MCP Rate Limiting Implementation 2026 (kansei-link): https://kansei-link.com/en/insights/mcp-rate-limiting-implementation-guide-2026
- MCP Schema Design (yaw): https://yaw.sh/mcp-in-production/mcp-schema-design/
- AWS MCP Tool Design: https://aws.amazon.com/blogs/machine-learning/mcp-tool-design-practical-approaches-and-tradeoffs/
- cyanheads MCP dev guide: https://github.com/cyanheads/model-context-protocol-resources/blob/main/guides/mcp-server-development-guide.md
- MCP Best Practices: Architecture & Implementation: https://modelcontextprotocol.info/docs/best-practices/
- arxiv — MCP Server Architecture Patterns: https://arxiv.org/abs/2606.30317
- MCP Bundles — Six-Tool Pattern: https://www.mcpbundles.com/blog/mcp-tool-design-pattern
- blockchain-council — Reliable MCP Tools: https://www.blockchain-council.org/claude-ai/designing-reliable-tools-mcp-server-claude-schemas-validation-error-handling/
- Clever Cloud — Building Smarter MCP Servers: https://www.clever.cloud/blog/engineering/2025/10/01/building-smarter-mcp-servers/
- Peliqan — MCP Rate Limits: https://peliqan.io/blog/mcp-rate-limits-guide/
- Zuplo — Rate Limit at the Edge: https://zuplo.com/blog/never-ship-mcp-server-without-rate-limit
- Tool annotations (mcpblog): https://mcpblog.dev/blog/2026-03-13-mcp-tool-annotations
- JSON Schema in MCP: https://www.devshelfhub.com/tutorials/mcp/schema/
