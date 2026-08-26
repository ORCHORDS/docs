# fetchLater deferred telemetry and quota control

**Issue:** An application relies on unload-time fetch or a large beacon to send critical state. Navigation ends before transmission, payloads exceed user-agent budgets, or retries create duplicate analytics events. A new deferred request API is then adopted without accounting for activation, quota, body, and policy constraints.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** emerging Fetch API; feature-detect and retain fallback

## Problem and applicability

The Fetch Standard defines fetchLater for scheduling a deferred fetch that the user agent can activate after a requested delay or when the document is being discarded. It returns a result whose activated state can be observed. The mechanism is constrained by secure-context, permissions-policy, request-body, and per-context quota rules.

Use it for small, loss-tolerant telemetry or best-effort notifications. Do not use it for payment, consent, logout revocation, draft durability, or any write whose correctness requires acknowledged delivery.

## Controls and implementation

1. Feature-detect window.fetchLater and keep the ordinary in-session batching/fetch path as primary. Use sendBeacon or keepalive fetch only according to their own documented limits where a fallback is appropriate.
2. Create a compact, already-serialized body with known length. Do not pass a streaming ReadableStream or defer expensive serialization until page teardown.
3. Set activateAfter only when the event can tolerate that delay. Treat activation timing as user-agent controlled and never schedule a client-side deadline that the server relies on.
4. Stay well below current deferred-fetch quota and payload limits. Catch synchronous and promise/API errors such as quota or policy rejection, then keep the event in the next normal batch rather than spinning.
5. Configure deferred-fetch Permissions Policy narrowly, including the reduced allowance intended for cross-origin/minimal-quota use. Prefer a same-origin collector that forwards server-side.
6. Give every event or batch a stable identifier. The collector must deduplicate because fallback, activation ambiguity, navigation restore, and application retry can deliver more than once.
7. Observe activated only as local lifecycle telemetry. It does not prove the server received, accepted, or persisted the request.
8. Minimize credentials and personal data. Apply consent before queueing, honor revocation in the server pipeline, and never place secrets in URLs.
9. Bound outstanding requests per page and coalesce superseded analytics. A quota-exhaustion loop can degrade navigation and still lose data.

## Verification

Test unsupported API, immediate and delayed activation, navigation and tab discard, back-forward cache, abort before activation, already-activated abort, known-size body, streaming-body rejection, same- and cross-origin policy, quota exhaustion, offline mode, collector timeout, duplicate fallback delivery, consent revoked, and server deduplication.

Confirm the page remains correct when no request arrives, activated never becomes a delivery acknowledgment, and telemetry loss is measured only through server-side accepted batch identifiers.

## Gotchas

- Deferred does not mean guaranteed, durable, background, or exactly once.
- User-agent quota is shared and specification/browser behavior can evolve.
- URL/query data can leak through logs even when the body is protected.
- Lifecycle APIs are unsuitable for irreversible business state.

## Official sources

- [WHATWG Fetch — fetchLater](https://fetch.spec.whatwg.org/#dom-window-fetchlater)
- [WHATWG Fetch — Deferred fetching](https://fetch.spec.whatwg.org/#deferred-fetch)
