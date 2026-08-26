# MCP URL elicitation trust boundary

**Issue:** MCP elicitation can direct a user to an external interaction URL. This is a user-consent and phishing boundary: the model must not represent navigation or completion as proof that an external action was authorised or succeeded.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Display the destination origin before navigation, restrict allowed schemes, and require explicit user action.
- Bind completion to an opaque, expiring state value and verify it server-side; never put bearer tokens or sensitive form data in the URL.
- Separate an elicitation response from the later tool call that consumes verified results.

## Verification

1. Reject lookalike origins, scheme confusion, open redirects, reused state, expired state, and unsolicited callbacks.
2. Cancel mid-flow and prove no mutating tool action occurred.
3. Test a client that does not support URL elicitation.

## Gotchas

Elicitation is not authentication. Treat the MCP specification version and feature support as negotiated capabilities, and label experimental/draft behavior where the official specification does.

## Official sources

- https://modelcontextprotocol.io/specification/2025-06-18/client/elicitation
