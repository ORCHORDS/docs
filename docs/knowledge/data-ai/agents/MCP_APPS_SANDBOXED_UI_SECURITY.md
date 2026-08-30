# MCP Apps Sandboxed UI Security

## Purpose

MCP Apps is an official MCP extension for server-rendered interactive user interfaces. In the 2026-07-28 protocol generation, servers can declare UI templates that a host renders in a sandboxed iframe while UI-initiated actions continue through MCP's normal JSON-RPC control path.

## Security model

A UI supplied by an MCP server is untrusted application content from the host's perspective. Sandboxing limits what that content can access directly, while host-mediated protocol calls preserve the same consent, authorization, logging, and tool-execution controls used for ordinary MCP requests.

## Practical controls

1. Render server-supplied interfaces in a restrictive sandbox rather than the host application's primary origin.
2. Prefetch and review declared UI templates before execution where the host supports that workflow.
3. Keep UI-triggered tool calls on the same authenticated and authorized MCP path as non-UI tool calls.
4. Do not expose host secrets, bearer tokens, cookies, filesystem access, or privileged browser APIs to the sandboxed application.
5. Validate message origins and protocol envelopes for communication between the iframe and host.
6. Apply Content Security Policy and network restrictions appropriate to the host's threat model.
7. Treat displayed HTML and remote resources as untrusted input even when they came from an authenticated MCP server.
8. Preserve an auditable record of user consent and privileged actions initiated from an MCP App.

## Current protocol context

MCP Apps became part of the formal extensions model associated with the 2026-07-28 specification. The release candidate describes servers shipping interactive HTML interfaces that hosts render in sandboxed iframes, with UI actions going through the same JSON-RPC base protocol and audit/consent path as direct tool calls.

## Sources

- Model Context Protocol — 2026-07-28 specification release: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- Model Context Protocol — 2026-07-28 release candidate, MCP Apps: https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/

## Scope note

Sandboxing is one layer of isolation. Host applications still need secure origin handling, authorization, consent, data minimization, and browser-security controls.
