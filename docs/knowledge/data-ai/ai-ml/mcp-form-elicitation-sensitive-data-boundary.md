# MCP Form Elicitation Sensitive-Data Boundary

**Issue:** MCP form elicitation can look like a trusted product dialog even though the request originates at a server. Using it for credentials or coercive consent creates a phishing and data-exfiltration channel.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls
- Use form mode only for the protocol's restricted, flat object schema and validate every requested property before rendering.
- Do not request passwords, API keys, access tokens, payment credentials, private keys, recovery codes, or other sensitive information through form elicitation.
- Show the requesting server identity, purpose, fields, and destination before input. Preserve clear accept, decline, and cancel actions.
- Treat `decline` and `cancel` as final for that interaction; do not loop, shame, or silently convert them into acceptance.
- The client validates the request schema before display, and the server validates accepted content again before use. Apply length, enum, numeric-range, and business-rule checks.
- Minimize retention and telemetry. Never place submitted values in traces, model context, analytics, or error messages unless explicitly required and protected.

## Verification
- Inject unsupported schema keywords, nested objects, secret-like fields, and oversized descriptions; the client refuses to render them.
- Confirm decline and cancel cause no side effect and no value is sent.
- Inspect logs and traces after an accepted form and verify submitted values are absent or deliberately redacted.

## Gotchas
Use URL elicitation for interactions that require a separately authenticated web flow. A form rendered by the client is not a credential vault.

## Official sources
- https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation
