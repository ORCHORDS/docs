# Workers passThroughOnException Body-Reuse Boundary

**Issue:** A fail-open Worker can consume a streaming request body and then throw. The runtime cannot replay that consumed body to the origin, so a non-idempotent request may arrive empty or fail with a misleading client error.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls
- Enable `ctx.passThroughOnException()` only for routes where bypassing Worker logic is an explicitly accepted availability and security tradeoff.
- Avoid consuming or transforming the request body before the point at which runtime pass-through may be needed.
- Catch origin `fetch()` failures yourself and return a deliberate `5xx` response; do not rely on runtime fallback after an origin fetch may have consumed the body.
- Fail closed for authentication, authorization, payment, mutation, upload, and policy-enforcement routes unless a reviewed origin control provides equivalent protection.
- Log which routes enable pass-through and test them with streamed `POST`, `PUT`, and upload bodies.
- Design a separate safe fallback for CPU or memory limit failures because pass-through protects uncaught code exceptions, not resource-limit termination.

## Verification
- Send a streamed mutation body, consume it, then throw in a test deployment; confirm the route does not silently perform an empty origin mutation.
- Inject origin connection failures and assert the Worker emits the intended `5xx` response.
- Audit every call site against a route inventory and security-owner approval.

## Gotchas
Request and response bodies are streamed, not automatically buffered. `passThroughOnException()` is not a general high-availability switch.

## Official sources
- https://developers.cloudflare.com/workers/runtime-apis/context/
