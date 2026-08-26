# AsyncAPI Request-Reply Dynamic Address Contract

**Issue:** Request-reply messaging becomes non-portable when reply destinations are implied by broker convention instead of expressed in the contract.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Represent the reply on the initiating operation and reference a reply channel containing only valid reply messages.
- When the destination is determined at runtime, define an Operation Reply Address expression that resolves from the request message.
- Keep a dynamically addressed reply channel's static address absent or null as required by AsyncAPI 3.
- Specify timeout, correlation, authorization, delivery multiplicity, and late-reply behavior outside the schema.
- Constrain untrusted reply destinations to permitted broker namespaces or address patterns.

## Verification

- Resolve the reply address from valid and malformed requests and reject unauthorized destinations.
- Test timeout, duplicate reply, late reply, responder failure, and mismatched correlation.
- Validate protocol bindings for temporary queues, topics, or reply-to headers against deployed broker behavior.

## Gotchas

- Validate feature and specification maturity against the cited official source.
- Avoid secrets, personal data, and restricted operational details in examples or evidence.
- Reassess after scope, dependency, protocol, or policy changes.

## Sources

- https://www.asyncapi.com/docs/reference/specification/v3.0.0
