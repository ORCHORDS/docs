# Replay-Resistant Webhooks for Agent Events

## Scope

Agent systems use webhooks to deliver task completion, approval requests, external updates, and tool callbacks. A webhook endpoint exposed to the internet must authenticate the sender, protect message integrity, constrain replay, and make repeated delivery safe. This article defines a protocol-neutral design grounded in HTTP Message Signatures, digest fields, and standard HTTP semantics. It does not claim that every webhook provider implements these specifications; deployments must follow the provider's documented scheme when different.

Replay resistance and idempotency solve different problems. Replay controls reject reuse of an authenticated message outside policy. Idempotency ensures that legitimate retries do not repeat a business side effect. A robust receiver needs both.

## Implementation workflow

Register each sender with an identity, accepted signing keys, algorithms, endpoint, and event classes. Define a signing profile that covers the HTTP method, target, authority where stable, content digest, content type, creation time, expiration, nonce or event ID, and subscription identifier. If using another established provider signature format, document its equivalent coverage and limitations.

Receive the body under a strict byte limit without transforming it. Validate `Content-Digest` where the profile uses RFC 9530, then verify the message signature and required covered components. Resolve keys from trusted registration or authenticated metadata, never from an arbitrary URL in the request. Enforce a narrow freshness window using synchronized clocks.

Atomically claim the sender-scoped event ID or nonce in durable storage before processing. The claim record includes payload digest and status. If the same identity and event ID arrive with the same digest, return the documented duplicate outcome without repeating effects. If the digest differs, treat it as a conflict and security signal.

Acknowledge only according to the delivery contract. For longer processing, durably enqueue the verified event and return success after the queue commit. The worker rechecks subscription state, tenant binding, event schema, and resource authorization before applying an idempotent state transition.

## Controls

Use TLS and restrict methods and content types. Separate webhook endpoints from interactive sessions; ignore cookies and browser authentication. Keep signing keys per sender or trust domain and support overlap during rotation. Disable subscriptions independently from deleting replay records.

Bound replay storage by the maximum accepted message lifetime plus retry horizon, while preserving business idempotency records as long as duplicate effects remain possible. Enforce payload schemas and reject unknown event types. Treat human-readable event content as untrusted and never execute instructions embedded in it.

Apply rate limits by sender and endpoint, but ensure forged traffic cannot exhaust expensive cryptographic or database paths unchecked. Use edge byte limits and inexpensive syntax checks first without creating timing shortcuts that reveal registered identities.

## Validation evidence

Test valid delivery, exact retry, same ID with changed body, changed method or path, bad digest, bad signature, unknown trusted key, stale and future timestamps, nonce reuse, disabled subscription, out-of-order events, concurrent duplicates, queue commit failure, handler crash, and key rotation. A concurrency test should prove that only one worker obtains the event claim.

Retain the signing profile, sender registry history, replay and idempotency retention settings, clock monitoring, schema versions, endpoint access rules, and redacted test captures. Evidence should connect a webhook event to exactly one committed state transition. Verify that duplicate success responses reveal no sensitive processing details.

## Failure handling

Reject unauthenticated, altered, stale, or conflicting events before enqueueing. Use stable HTTP outcomes appropriate to the sender contract and avoid detailed cryptographic errors. On transient internal failure before durable acceptance, return a retryable failure. After durable acceptance, retries should observe the same event state rather than create new work.

If a signing key is compromised, disable it, rotate registration, suspend sensitive event handling, and inspect accepted events in the exposure window. Reconcile side effects using event IDs and payload digests. If replay storage is unavailable, fail closed for consequential events; do not process and promise later deduplication.

## Canonical sources

- RFC 9421, HTTP Message Signatures: https://www.rfc-editor.org/rfc/rfc9421
- RFC 9530, Digest Fields: https://www.rfc-editor.org/rfc/rfc9530
- RFC 9110, HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110
