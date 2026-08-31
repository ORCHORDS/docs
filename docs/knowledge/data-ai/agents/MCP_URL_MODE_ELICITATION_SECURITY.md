# MCP URL-Mode Elicitation Security

## Purpose

MCP protocol revision 2025-11-25 introduced URL-mode elicitation for sensitive interactions that must not pass through the MCP client, such as credential entry, third-party OAuth authorization, or payment flows.

## Form mode versus URL mode

MCP servers must not use form-mode elicitation to request sensitive secrets such as passwords, API keys, access tokens, or payment credentials. Those interactions must use URL mode so the sensitive data is entered in an external secure context rather than exposed to the MCP client or model.

URL mode is not the mechanism for authorizing the MCP client's own access to the MCP server. The client's bearer token remains governed by MCP authorization separately.

## Client controls

A client supporting URL mode should:

1. declare URL-mode elicitation capability during initialization;
2. make it clear which MCP server is requesting the interaction;
3. display the full target URL or domain for user examination;
4. obtain explicit user consent before navigation;
5. never automatically prefetch the URL or its metadata;
6. open the target in a secure context that prevents the MCP client or model from inspecting the user's sensitive inputs; and
7. always give the user a practical way to decline, cancel, or manually retry the workflow.

## Server controls

A server requesting URL elicitation must bind the request to the relevant client and user context. The URL must not contain sensitive end-user information and must not be pre-authenticated to a protected resource.

The server should use HTTPS outside development environments and should verify the identity of the user who opens the URL so that an elicitation link forwarded to another person cannot be used to complete authorization for the wrong account.

## Completion and retry behavior

A successful `elicitation/create` response with `action: "accept"` means only that the user agreed to navigate to the URL; it does not mean the external interaction is complete.

The server may send `notifications/elicitation/complete` using the original `elicitationId`. Clients must ignore completion notifications for unknown or already-completed IDs and should preserve manual retry/cancel controls in case the completion notification never arrives.

When the original MCP operation cannot continue until the external interaction is finished, a server may return `URLElicitationRequiredError` with code `-32042`. Required elicitations in that error must be URL-mode elicitations.

## Sources

- Model Context Protocol Specification 2025-11-25 — Elicitation: https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation
- Model Context Protocol 2025-11-25 Changelog: https://modelcontextprotocol.io/specification/2025-11-25/changelog

## Scope note

URL-mode elicitation moves sensitive data out of the MCP client, but it does not by itself secure the external website, third-party authorization server, payment provider, or user session. Those systems require their own authentication, authorization, anti-phishing, privacy, and transaction controls.