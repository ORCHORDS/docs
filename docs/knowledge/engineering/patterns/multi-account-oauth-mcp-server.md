# multi-account-oauth-mcp-server

**Issue:** A local MCP stdio server (gmail-mcp-connector) must act on behalf of MULTIPLE accounts of the SAME upstream provider — a work Gmail and a personal Gmail — but the MCP authorization spec only models one identity axis: a remote MCP server acting as a single OAuth 2.1 resource server. It has no concept of a local server holding N token sets for N accounts of one provider, and the spec's multi-user question is still an open discussion ([modelcontextprotocol#234](https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/234)). We closed the gap with a first-hand pattern: stable label-based account identity, one token file per account on disk, a default-account concept for ergonomic tool calls, and connect/disconnect flows that run OUTSIDE the server (a stdio server's stdout belongs to JSON-RPC, so the OAuth browser+loopback dance must execute in a separate terminal via a CLI subcommand the server merely tells the user to paste).

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## When you need this pattern

1. **One person, several identities at one provider.** The user wants "search work Gmail" and "search personal Gmail" from the same agent session. Single-token MCP auth designs (one env var, one OAuth dance) force constant re-login or a second server instance per account.
2. **The spec models resource-server auth, not account multiplexing.** The 2025 MCP authorization spec (OAuth 2.1, PKCE, RFC 8707 resource indicators) governs a client authenticating TO a remote MCP server; it says nothing about a local server authenticating to N accounts of an upstream API. Existing coverage in `documentation/docs/policies/patterns/mcp-auth-2026.md` stops at the remote-server case — this pattern is the local multi-account complement.
3. **Community convergence.** Production writeups ([multi-user MCP auth for enterprise agents](https://medium.com/@atul/bringing-mcp-auth-to-production-solving-the-two-hop-problem-854a25980f9f), [Box's per-user OAuth MCP](https://blog.box.com/securing-your-mcp-servers), [Maxim's MCP auth overview](https://www.getmaxim.ai/articles/mcp-authentication-explained-oauth-api-keys-and-token-management/)) all land on the same shape we built independently: an account/user identifier as a tool-call parameter, plus token storage keyed by that identifier. The [Doppler critique of static single tokens](https://www.doppler.com/blog/map-servers-auth-static-tokens) explains why the naive alternative fails.

## Account identity model

1. **Labels, not emails, as the primary key.** Each account gets a short stable label (`work`, `personal`) chosen at connect time. The label is the key in config, token files, and every tool argument; the email is display metadata stored inside the token record.
2. **Why not email-keyed.** Emails are PII — keying by email bleeds addresses into tool-call logs and agent transcripts, and emails can change or be aliased (`user+tags@`). Labels never change and are trivial to type as an enum in a tool schema.
3. **Labels are an enum in tool schemas.** Exposing `account` as an enum of configured labels (not a free string) lets the host model validate before the call and prevents a typo'd account from becoming a stored-but-unreachable token file.
4. **Default account.** Config marks exactly one label as default. Every account-taking tool omits `account` meaning "use default"; a `set-default` action switches it. This keeps the 90% single-account interaction ergonomic — no `account` argument at all.

## Per-account token storage on disk

1. **One file per label.** Layout like `~/.gmail-mcp/tokens/<label>.json` holding access token, refresh token, expiry, granted scopes, and the account email for display. Deleting one file disconnects exactly one account; no multi-account blob to corrupt.
2. **Atomic writes, restrictive perms.** Token refreshes happen at runtime, so writes must be tmp-file-plus-rename (a half-written token file would log the user out), and the file should be readable only by the user (0600 / restricted ACL) — refresh tokens are long-lived bearer secrets.
3. **Read per call, not cached forever.** The server reads the token file when a tool call needs it (with a short-lived in-memory cache keyed by mtime). This means a token connected by the CLI a second ago is immediately visible to the already-running server with no restart handshake.
4. **Never tokens in server config.** The MCP host config contains only `command`/`args`. Tokens in host JSON configs get copied into screenshots, dotfile repos, and support tickets; token files in a user-only directory do not.

## Connect/disconnect must run outside the stdio server

1. **stdio stdout is owned by JSON-RPC.** The OAuth dance needs a browser, a `127.0.0.1` loopback redirect listener, and a consent screen — a long-running interactive flow. Running it inside a stdio server blocks the protocol channel (the host is waiting for `initialize` responses, not progress logs about a browser tab).
2. **The server returns the command; the user pastes it.** The connect tool's job is to emit the exact one-liner for the human to run in a separate terminal — `gmail-mcp connect <label>` — including any flags, and then tell them to re-run their intended call. The loopback flow binds its port in that terminal process, completes the code exchange, and writes `tokens/<label>.json`.
3. **Disconnect is revoke-then-delete.** Disconnecting an account must revoke the grant at the provider's revocation endpoint AND delete the local token file; doing only the latter leaves a live grant on the Google account security page.
4. **Same binary, two entrypoints.** Ship the stdio server and the CLI subcommands (`connect`, `disconnect`, `list`) from one package — they share the token store code, so there is exactly one implementation of "what a valid token file looks like."

## Tool surface design

1. **Optional `account` on every provider-scoped tool.** All Gmail tools accept an optional `account` (enum of labels); omitting it targets the default. Server-level tools (`list_accounts`, `set_default_account`, `get_connect_command`) never take one — they operate on the store.
2. **`list_accounts` is the discovery surface.** It returns labels, masked emails (`j***@gmail.com`), which label is default, and per-account token health (valid / expired / needs reconnect). Hosts and users route from here.
3. **Actionable errors on the unhappy path.** Calling with an unknown label, or hitting an expired refresh token, must return an error that names the exact fix: "account `work` not connected — run `gmail-mcp connect work` in a terminal." A bare `invalid_grant` error wastes an entire debugging round-trip.
4. **Log labels, not emails.** Whatever logging the server emits should reference accounts by label; the mapping label→email lives only in the token files and `list_accounts` output.

## Edge cases and security

1. **Connecting the same provider account under two labels.** Allow or reject explicitly (we allow it — forwarding filters differ), but `list_accounts` should make the duplication visible, or the user will wonder which copy is stale.
2. **Refresh-token rotation.** If the provider rotates refresh tokens on use ([the MCP spec expects rotation for public clients](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/authorization)), every rotation rewrites the token file — another reason writes must be atomic and the cache mtime-keyed.
3. **Two flows racing.** A tool call refreshing a token while the CLI rewrites the same file is the one real concurrency hazard; rename-based atomic writes plus "last writer wins, next call re-reads" keeps it benign.
4. **Minimal scopes per account.** Each account connects with only the scopes its label needs (e.g. `gmail.readonly` for a search-only label) — multi-account multiplies blast radius, so least-privilege is per-account, not per-server.
