# MCP sampling tool-capability negotiation

**Issue:** MCP sampling may let a server request model generation and, in newer capability shapes, tool use. A server request must not silently inherit every client tool or approval policy.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Negotiate exact capability/version; expose a per-server tool allowlist; retain client-side consent and budgets; validate tool schemas/results and bind every mutation to user-visible approval.

## Verification

Test clients with no sampling, sampling without tools, unknown tools, nested sampling, cancellation, token exhaustion, and malicious tool descriptions.

## Gotchas

Sampling reverses the usual call direction and is a privilege escalation surface. Model output and requested tool calls remain untrusted.

## Official sources

- https://modelcontextprotocol.io/specification/2025-06-18/client/sampling
