# mcp-auth-2026

- **Issue**: Public remote MCP servers MUST implement OAuth 2.1 with PKCE since the November 2025 spec. The two most-skipped requirements — Resource Indicators (RFC 8707) and PKCE S256 — are also the most-exploited. Build the auth wrong and you ship a confused-deputy hole.
- **Date**: 2026-08-09
- **Repo**: example-org/example-repo
- **Author**: kb-batch-2
- **Status**: Active; complements `documentation/categories/patterns/mcp-server-patterns.md`.

## Symptom

- A token issued for `mcp-A.example.com` is replayed against `mcp-B.example.com` and accepted. Cross-server escalation.
- The MCP client is a public desktop app but the server is using a static client secret. The secret leaks. The whole fleet is compromised.
- An attacker intercepts the authorization code, redeems it at the token endpoint, and gets a token for the legitimate user. PKCE would have blocked this; you didn't require it.
- Token is sent in the URL query string and ends up in server logs. Bearer tokens in URI query strings are forbidden by OAuth 2.1.

## Root cause

MCP is the Model Context Protocol. Remote MCP servers are OAuth **resource servers**: they accept bearer tokens issued by a separate authorization server. The auth spec was rewritten in the June 2025 revision around OAuth 2.1 (IETF draft 13), with explicit MUSTs around PKCE, Resource Indicators, and discovery. The November 2025 spec made the requirements explicit and mandatory for any public remote MCP.

## The non-negotiable spec (verbatim from the 2025-11-25 MCP authorization spec)

- **Auth basis**: OAuth 2.1 IETF draft 13 + RFC 9728 (Protected Resource Metadata) + RFC 8414 (Authorization Server Metadata) + RFC 7591 (Dynamic Client Registration) + RFC 8707 (Resource Indicators).
- **Required for all clients**: PKCE. `S256` if technically capable; plain only when SHA-256 is impossible.
- **Required discovery**: `WWW-Authenticate: Bearer resource_metadata=…` on 401, or a well-known URI per RFC 9728. `/.well-known/oauth-authorization-server` per RFC 8414.
- **Required scope on every authorize and token request**: the `resource` parameter (RFC 8707), set to the canonical URI of the MCP server.
- **Forbidden**: implicit grant, ROPC password grant, plain-PKCE when S256 is feasible, bearer tokens in URI query strings, token passthrough to upstream APIs.
- **Should**: Dynamic Client Registration on both sides, refresh-token rotation for public clients, short-lived access tokens, exact-match redirect URIs.

## The discovery flow (every fresh MCP client)

1. **Probe** — Client → MCP server: `POST initialize` with no token. Server → Client: `401` with `WWW-Authenticate: Bearer resource_metadata=…`.
2. **Protected Resource Metadata** — Client → MCP server: `GET /.well-known/oauth-protected-resource`. Returns auth server URL + audience.
3. **AS Metadata** — Client → Auth server: `GET /.well-known/oauth-authorization-server`. Returns endpoints + capabilities.
4. **DCR (if needed)** — Client → Auth server: `POST /oauth/register`. Returns `client_id`.
5. **PKCE setup** — Client generates a 43–128 char `code_verifier` and `code_challenge = BASE64URL(SHA256(code_verifier))`.
6. **Authorize** — Client redirects user to `/authorize` with `code_challenge`, `code_challenge_method=S256`, `state`, and `resource=<mcp canonical uri>`.
7. **Code exchange** — Client → Auth server: `POST /token` with `code` + `code_verifier` + `resource`. Returns access token (+ rotated refresh token for public clients).
8. **Tool call** — Client → MCP server: `Authorization: Bearer <token>` on every `tools/call`. MCP server validates the token against the AS's JWKS or introspection endpoint.
9. **Revoke** — User revokes from the IdP consent screen. Refresh token invalidated; the next access-token expiry kills agent access.

## The nine things a compliant MCP server does

1. Serves Protected Resource Metadata at `/.well-known/oauth-protected-resource`.
2. Requires PKCE with `code_challenge_method=S256` and rejects `plain`.
3. Validates the `aud` claim against its exact canonical URI on every request.
4. Caches JWKS with a 5-minute TTL.
5. Rotates refresh tokens and revokes the family on detected replay.
6. Supports Dynamic Client Registration with rate limiting.
7. Returns `WWW-Authenticate` with `resource_metadata` on 401 so clients can auto-discover.
8. Enforces scopes at the tool boundary, not just at the transport layer.
9. Stores the `code_verifier` in memory only (not localStorage, not sessionStorage, not cookies).

## Why Resource Indicators matter (the confused-deputy)

Without RFC 8707, a token issued for `mcp-A.example.com` can be replayed against `mcp-B.example.com` by any client that holds it. The MCP server has no way to know the token was not meant for it. The fix is **one line of validation code** — verify the `aud` claim contains your server's exact canonical URI — but it requires the auth server to bind the `aud` claim to the resource indicator sent in the authorization request.

The MCP spec explicitly forbids token passthrough: an MCP server that accepts a token issued for a different audience is a confused-deputy hole, and the spec calls that out by name.

## The storage rule for `code_verifier`

The verifier must be stored **in memory only**. Not in localStorage, not in sessionStorage, not in a cookie, not in any persistent storage. An attacker who can read persistent storage can recover the verifier and use it to exchange an intercepted authorization code. The verifier should be held in a module-scoped variable for the duration of the authorization flow and explicitly cleared after the token exchange completes, regardless of outcome.

## JWKS caching

Do not call the auth server's introspection endpoint on every request. Local JWT validation with a cached JWKS is the correct default. **5-minute TTL is the sweet spot**: short enough to pick up key rotation, long enough to keep validation under 1 ms. On `kid` miss, refresh once and then fail closed.

## Audience vs Resource Indicator

These are not redundant. **Audience validation** confirms the token's intended consumer category. **Resource Indicator validation** confirms the exact resource server. Reject tokens where either is missing or wrong.

## Why PKCE if you already have a client secret

PKCE protects the code exchange against interception even when the client is confidential. MCP clients are often desktop apps that cannot store secrets reliably. PKCE is non-optional. Plain PKCE is no longer allowed when S256 is technically capable.

## Use a hosted IdP

Picking WorkOS / Auth0 / Clerk / Cognito is fine; building it yourself is mostly a bad idea in 2026. They support the four primitives (PKCE S256, RFC 9728 metadata, RFC 8414 metadata, Resource Indicators) natively.

## Verification

- **Forged token test** — fixture a token signed by a wrong key; assert rejection.
- **Missing-`aud` test** — fixture a valid token without the resource indicator; assert rejection.
- **Wrong-`aud` test** — fixture a token for a different resource server; assert rejection.
- **Expired token test** — fixture an expired access token; assert rejection.
- **Replayed authorization code test** — assert one-time-use enforcement.
- **Plain-PKCE rejection test** — assert the server rejects `code_challenge_method=plain` even when S256 is feasible.
- **JWKS rotation test** — rotate the key on the IdP, verify the server picks it up within the 5-minute TTL window.
- **Refresh-token rotation test** — verify a refresh token works once and is invalidated after.
- **Refresh-token family revocation test** — assert that replaying an old refresh token kills the whole family.

## Gotchas

- **Implicit grant and ROPC are gone.** Don't reach for them.
- **Bearer tokens in URI query strings are forbidden.** Always `Authorization: Bearer …`.
- **Token passthrough is the confused-deputy.** Don't accept a token issued for another audience, even if it parses.
- **Plain PKCE is no longer acceptable** when S256 is feasible. Reject it server-side.
- **`code_verifier` in localStorage** is a vulnerability, not a feature. Memory only.
- **JWKS cache TTL matters.** 5 min is the sweet spot. < 1 min thrashes; > 15 min delays rotation.
- **Audience validation alone is not enough.** You also need resource indicator validation.
- **Don't implement your own IdP** unless you have a strong reason. WorkOS, Auth0, Clerk, Cognito all ship the right primitives.
- **Scopes at the tool boundary**, not just the transport layer. A bearer token for `mcp:read` should not be able to call `delete_file`.
- **DCR with rate limiting.** Unauthenticated DCR is a DoS vector.
- **Streamable HTTP transport is the default now** (since 2025-03-26). The older HTTP+SSE two-endpoint transport is deprecated. OAuth 2.1 hardening is the 2025-06-18 revision.

## Related

- `documentation/categories/patterns/mcp-server-patterns.md` — the broader server design
- `documentation/categories/security/ai-agent-security.md` — the threat model
- `documentation/categories/security/prompt-injection-defense.md` — what to do when auth is bypassed
- `documentation/categories/cloudflare/agents-sdk-best-practices.md` — a Cloudflare-native MCP path

## Source URLs (verified 2026-08-09)

- MCP Authorization spec (2025-11-25) — https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization
- "OAuth 2.1 for Remote MCP Servers (2026)" (mcp.directory) — https://mcp.directory/blog/oauth-21-for-remote-mcp-servers-streamable-http-explained-2026
- "MCP Server Auth in 2026: OAuth 2.1, PKCE S256" (callsphere) — https://callsphere.ai/blog/vw4g-mcp-server-auth-oauth-2-1-pkce-authorization-spec-2026
- "MCP Server Authentication in .NET" — https://pabasara-mahindapala.github.io/dotnet/security/authentication/aspnetcore/2026/05/02/mcp-server-oauth2-dotnet/
- "Understanding MCP Authentication" (truefoundry) — https://www.truefoundry.com/blog/mcp-authentication
- "MCP Server OAuth 2.1 Setup: Implementation Checklist for 2026" (m2ml) — https://m2ml.ai/post/mcp-server-oauth-21-setup-implementation-checklist-for-2026-cms66hzn90bzj11mp81k9b73q
- "MCP OAuth 2.1: PKCE, Scopes & Token Management" (practical-devsecops) — https://www.practical-devsecops.com/mcp-oauth-2-1-implementation/
- RFC 8707 (Resource Indicators) — https://www.rfc-editor.org/rfc/rfc8707.html
- RFC 9728 (Protected Resource Metadata) — https://datatracker.ietf.org/doc/html/rfc9728
- RFC 8414 (Authorization Server Metadata) — https://datatracker.ietf.org/doc/html/rfc8414
- OAuth 2.1 IETF draft — https://datatracker.ietf.org/doc/html/draft-ietf-oauth-v2-1-13
