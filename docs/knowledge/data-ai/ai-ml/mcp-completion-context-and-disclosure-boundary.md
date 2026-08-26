# MCP Completion Context and Disclosure Boundary

**Issue:** An MCP completion endpoint is often called on every keystroke. If it treats suggestions as public discovery, ignores prior arguments, or returns unbounded values, it can leak resource names and create a denial-of-service path.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls
- Negotiate the server completion capability before using `completion/complete`; reject unknown prompt or resource-template references and unknown argument names.
- Authorize the referenced prompt or resource template for the current principal before computing suggestions. Return a non-enumerating result when access is absent.
- Treat `context.arguments` and the partial value as untrusted input. Validate length and shape, and use contextual arguments only to narrow results without widening authorization.
- Return at most 100 values as required by the protocol. Keep ranking deterministic and make `total` and `hasMore` truthful when supplied.
- Rate-limit and debounce per principal. If results are cached, include tenant, principal, reference, argument, context, and policy version in the cache key.
- Never suggest secrets, raw tokens, hidden identifiers, or the existence of objects the caller cannot read. Log reference IDs and outcome counts, not sensitive query text.

## Verification
- Exercise an authorized and unauthorized principal with the same prefix and confirm the latter learns no protected names or counts.
- Fuzz invalid references, oversized prefixes, and malformed context; each fails boundedly without invoking expensive downstream search.
- Confirm no response contains more than 100 values and stale or cancelled UI requests cannot overwrite a newer result.

## Gotchas
Completion is advisory UI data, not validation. A later prompt or resource request must independently validate and authorize the selected value.

## Official sources
- https://modelcontextprotocol.io/specification/2025-11-25/server/utilities/completion
