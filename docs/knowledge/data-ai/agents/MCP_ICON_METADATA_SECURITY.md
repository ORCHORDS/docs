# MCP Icon Metadata Security

## Purpose

MCP 2025-11-25 allows servers and clients to attach icon metadata to implementations, tools, prompts, resources, and resource templates. Icons improve UI discoverability, but they also introduce network-fetch, parsing, privacy, and resource-exhaustion risks.

## Current protocol requirements

An MCP icon contains a source URI and can include MIME type, size hints, and a light/dark theme preference. Clients that render icons must support PNG and JPEG. They should also support SVG and WebP, with additional precautions for active or complex formats such as SVG.

The specification requires consumers to treat icon metadata and bytes as untrusted input.

## Fetch policy

1. Allow only HTTPS or `data:` icon URIs.
2. Reject unsafe schemes such as `javascript:`, `file:`, `ftp:`, WebSocket schemes, and local-application URI schemes.
3. Do not follow redirects that change scheme or move to a different origin.
4. Fetch remote icons without cookies, authorization headers, or client credentials.
5. Prefer icons from the same origin as the MCP server so rendering does not disclose client activity to unrelated third parties.
6. Apply connection, download-size, and timeout limits.

## Content validation

- Treat the declared MIME type as advisory.
- Inspect file signatures or other trusted content-type evidence before rendering.
- Reject mismatches between declared and observed types.
- Maintain a strict allowlist of image formats.
- Bound decoded dimensions, frame counts, and memory use to resist decompression or animation bombs.
- Sanitize or disable executable SVG features where SVG rendering is supported.

## Privacy considerations

A remote icon request can reveal that a client connected to a particular MCP server, viewed a tool, or opened a prompt. Same-origin fetching and credential-free requests reduce tracking risk.

Clients that need stronger privacy can proxy, cache, or disable remote icon fetches according to their threat model.

## Trust boundary

An icon does not authenticate the tool, resource, or server it depicts. Familiar brand artwork must never influence authorization decisions. Security-sensitive UI should bind identity to cryptographic/session evidence rather than visual metadata.

## Failure modes

- Rendering arbitrary SVG without sanitization can expose active-content risks.
- Following cross-origin redirects can create tracking or server-side request risks.
- Sending user cookies or tokens when fetching icons leaks credentials to icon hosts.
- Trusting file extensions or declared MIME type alone can render unexpected content.
- Unbounded image size or animation can create memory/CPU denial of service.

## Sources

- Model Context Protocol — Basic protocol overview and icon security, revision 2025-11-25: https://modelcontextprotocol.io/specification/2025-11-25/basic
- Model Context Protocol — Schema reference: https://modelcontextprotocol.io/specification/2025-11-25/schema
- Model Context Protocol — 2025-11-25 changelog: https://modelcontextprotocol.io/specification/2025-11-25/changelog

## Scope note

This article covers client-side handling of MCP icon metadata. Browser, desktop, and mobile rendering stacks may require additional format-specific sandboxing.