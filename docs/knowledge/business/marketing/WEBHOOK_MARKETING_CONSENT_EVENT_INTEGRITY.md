# Webhook Marketing Consent Event Integrity

## Scope

This control governs webhook delivery, receipt, validation, reconciliation, and correction for marketing consent events. It applies when consent, objection, unsubscribe, preference, suppression, double opt-in, source update, or permission-state events are transmitted between consent management platforms, customer data platforms, marketing automation systems, CRMs, data warehouses, and internal preference services. The control covers event structure, authenticity checks, idempotency, ordering, audit evidence, failure handling, and reconciliation. It does not determine whether a specific consent model is legally sufficient, whether a notice is adequate, or whether marketing is permitted in a jurisdiction. Those questions require separate legal and privacy governance.

Webhook integrity depends on reliable event metadata, transport handling, and verification. The CloudEvents specification provides a common event metadata model for identifying and routing events: [CloudEvents Specification repository](https://github.com/cloudevents/spec). W3C Trace Context defines HTTP headers and value formats for propagating request context in distributed systems: [W3C Trace Context Recommendation](https://www.w3.org/TR/trace-context/). HMAC is described by the RFC Editor as a keyed-hashing mechanism for message authentication: [RFC 2104, HMAC: Keyed-Hashing for Message Authentication](https://www.rfc-editor.org/info/rfc2104/). These primary sources support event metadata, traceability, and message integrity concepts. They do not provide a complete marketing consent compliance program.

## Required Fields And Controls

Every consent webhook event must contain an event identifier, event type, event creation time, event source, subject identifier, consent state, consent purpose or channel, evidence reference, source system, and delivery attempt metadata. The event identifier must be globally unique or unique within a documented source namespace. Event type values must come from a controlled list such as `marketing_consent_granted`, `marketing_consent_withdrawn`, `email_unsubscribed`, `sms_opted_out`, `preference_updated`, `double_opt_in_confirmed`, or `suppression_added`. The subject identifier must be a stable internal identifier or a protected contact key; raw email or phone values should be minimized in transit and avoided when a tokenized identifier can support the workflow.

Consent state must be explicit. Values such as `true`, `yes`, or `active` are not enough unless mapped to a purpose, channel, jurisdictional context if used internally, and evidence source. Required business fields include `purpose`, `channel`, `brand`, `region` where relevant, `collection_point`, `policy_version` where maintained, `capture_timestamp`, `effective_timestamp`, and `actor_type` such as user, agent, system, import, or administrator. Required operational fields include `idempotency_key`, `schema_version`, `producer`, `signature` or equivalent authentication evidence, `delivery_timestamp`, and `traceparent` or another correlation identifier if the organization uses distributed tracing.

Receiving systems must authenticate the sender, verify message integrity where a signature mechanism is configured, reject malformed payloads, enforce schema versions, and process idempotently. Idempotency is required because webhook senders commonly retry deliveries after timeouts or non-success responses. A duplicate `idempotency_key` must not create a second consent grant, a second unsubscribe, or a conflicting audit record. The receiver must preserve the original event and record processing status separately from business state. The most recent event is not always the correct event if effective times, source precedence, or user identity merge rules apply.

## Workflow

Webhook onboarding begins with a source-system registration. The registration records endpoint URL, event types, schema version, authentication method, retry behavior, timeout expectations, source owner, receiving owner, and reconciliation schedule. Security or platform engineering provisions secrets, certificates, OAuth clients, or network controls according to the organization’s integration standard. Marketing operations and privacy operations define the consent purposes, channels, and state transition rules that the integration may publish.

Before activation, producers and consumers exchange sample events for each material state transition. The receiving service validates schema, signature, idempotency, ordering behavior, and error responses. A test must include duplicate delivery, delayed delivery, missing optional fields, missing required fields, invalid signature, unknown event type, unsupported schema version, and conflicting state update. Production activation starts with limited volume or monitored rollout where feasible. During rollout, the team compares webhook-derived states with source-system reports.

Normal processing follows a durable sequence. The endpoint receives the event, records raw receipt metadata, verifies authenticity and schema, maps identifiers, evaluates state transition rules, updates the consent or suppression store, emits downstream events if approved, and records final processing status. Rejections must be explicit and observable. A successful HTTP response should mean the receiver accepted responsibility for processing according to the integration contract, not merely that a network request reached the endpoint.

## Validation Evidence And Tests

Required evidence includes the integration registration, schema definition, event type dictionary, authentication configuration, replay or idempotency design, test payloads, test results, production deployment approval, and reconciliation reports. For signature verification, evidence should include the algorithm family, header names, timestamp tolerance if used, secret rotation plan, and examples of accepted and rejected signatures. The evidence should not expose live secrets.

Automated tests must validate required fields, data types, timestamp formats, controlled enum values, unknown-field behavior, schema-version compatibility, and rejection of malformed JSON. Integrity tests must verify that a body changed after signing is rejected, an expired timestamp is rejected if timestamp binding is used, and an unknown key identifier fails closed unless a documented rotation window applies. Idempotency tests must prove that repeated events with the same key do not duplicate state changes. Ordering tests must prove the intended behavior for delayed withdrawal after grant, delayed grant after withdrawal, and source precedence conflicts.

Operational monitoring should track delivery count, acceptance count, rejection count, retry count, processing latency, dead-letter queue depth, signature failures, unknown schema versions, unmapped subject identifiers, and reconciliation variance. Reconciliation compares source-system consent states with the receiving preference store and downstream activation systems. Variance must be triaged by cause: delivery failure, processing failure, identity resolution failure, business-rule disagreement, or downstream propagation delay.

## Failures And Corrections

Common failures include accepting unsigned events, treating duplicate retries as new changes, losing events during deploys, overwriting withdrawals with older grants, failing to propagate suppression updates, and silently accepting unknown consent purposes. Another serious failure is logging raw contact identifiers or evidence payloads beyond approved retention or access boundaries. Corrections must be designed around preservation of the audit trail. The team should append correcting events or processing records rather than erasing the original facts, unless a separate data handling policy requires deletion.

If a withdrawal or unsubscribe event fails, the immediate correction is containment: pause affected outbound audiences where necessary, replay the missed event from the source of truth, and reconcile downstream systems. The incident record must identify the event IDs, affected purposes and channels, affected time window, systems updated, and residual uncertainty. If an invalid grant event was accepted, the team must determine whether downstream activation used it and remove or suppress the affected subject where appropriate.

Schema failures are corrected by versioning, not by silently changing field meanings. If a producer must add a field, the consumer should tolerate unknown fields if that is the contract. If a producer changes a required field meaning, a new schema version and migration plan are required. Authentication failures during secret rotation are corrected by a controlled overlap window with key identifiers, not by disabling verification.

## Requirements Versus Recommendations

Required: authenticate webhook sources; validate schema; require event IDs and idempotency keys; record raw receipt and processing status; preserve consent purpose and channel; reject unknown critical values; test duplicate, delayed, malformed, and invalid-signature events; reconcile source and receiver states; and document corrections.

Recommended: align event envelopes with CloudEvents concepts; propagate W3C trace context; use HMAC or stronger organization-approved message authentication; maintain dead-letter queues; provide replay tooling; alert on reconciliation variance; and separate personal identifiers from routing metadata.

## Limitations

Webhook integrity controls improve trust in event delivery and processing, but they do not prove that consent was lawfully collected, that disclosures were sufficient, or that downstream marketing is permissible. They also do not eliminate distributed-system uncertainty. Retries, outages, identity merges, clock skew, vendor delays, and manual imports can still create inconsistent states. The control requires evidence, reconciliation, and correction so those inconsistencies are detected and handled.

## Canonical sources

- **Primary authority 1 — CloudEvents Specification repository:** [https://github.com/cloudevents/spec](https://github.com/cloudevents/spec)
- **Primary authority 2 — W3C Trace Context Recommendation:** [https://www.w3.org/TR/trace-context/](https://www.w3.org/TR/trace-context/)
- **Primary authority 3 — RFC 2104, HMAC: Keyed-Hashing for Message Authentication:** [https://www.rfc-editor.org/info/rfc2104/](https://www.rfc-editor.org/info/rfc2104/)
