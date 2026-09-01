# Agent Dead Letter Triage

## Scope

This article covers the operational discipline for messages and tasks that arrive in an agent's dead-letter queue (DLQ). A DLQ is a holding area for items the system could not deliver or process after exhausting its normal retry and routing options. For an agent, those items typically include incoming A2A tasks that exceeded timeouts, incoming tool calls that could not be authorized, outgoing tool calls whose response was malformed, mid-task errors that could not be recovered by the agent itself, and external events that arrived after the agent's task window closed. Triage is the process of classifying each item, deciding whether and how to replay it, and either recovering it, discarding it, or escalating it for human review.

Out of scope: the implementation of the queueing system itself, choice of broker technology, and the agent's internal error handling during normal processing. This article treats the DLQ as a managed boundary between the agent runtime and human operators.

## Implementation workflow

The first step in triage is classification. Each DLQ item carries a triage envelope with the original task or message identity, the originating system, the failure category, the retry history, and any payloads or evidence captured at the point of failure. The triage process groups items into four classes: `recoverable`, `replayable-after-fix`, `permanent-failure`, and `policy-violation`. The classification is the basis for all subsequent action.

`recoverable` items are those whose failure cause is transient and has plausibly resolved. Examples include a downstream service returning 503 during a brief outage, a temporary DNS failure, an upstream rate limit that has reset, or a network partition that has healed. Triage re-injects these items at the head of the queue using the original task identity and a fresh delivery token. Replay is bounded: each item records how many times it has been re-injected from the DLQ, and items exceeding the configured re-injection cap are escalated.

`replayable-after-fix` items are those whose root cause is known but not yet fixed. Examples include a schema mismatch between the agent and a tool that requires a tool upgrade, a permission change that needs an operator to grant additional scopes, or a contract change between systems. Triage parks these items in a per-cause queue with the fix description; when the fix is deployed, the items are replayed in bulk. Each parked item must be inspected before park to confirm that bulk replay will not cause additional damage.

`permanent-failure` items are those that cannot succeed even with a fix. Examples include malformed input that the agent cannot parse, an authentication credential that has been revoked, a request from a sender that no longer exists, or a task that has been superseded by a newer request. Triage records the reason for permanent failure and routes the item to cold storage for retention per the data retention policy. The item is not deleted; it is archived with its triage decision so that future investigations can examine it.

`policy-violation` items are those whose handling would breach a security, privacy, or operational policy. Examples include content that matches a prompt-injection pattern, an authentication attempt from a non-allowlisted identity, a tool call that requires a scope the agent does not hold, or a request that would exceed the agent's data residency boundary. Triage does not replay these items; it routes them to security review and notifies the relevant operator.

Replay operations must be idempotent. The agent runtime treats every replayed item as a new attempt, but the underlying task handlers must be idempotent so that a duplicate replay does not cause duplicate side effects. The idempotency article in this family covers the broader discipline.

## Controls

Every triage action must be authorized and audited. Operators with DLQ triage privilege must authenticate with strong credentials; multi-party authorization is appropriate for replaying high-blast-radius items. Each triage decision is recorded as a signed audit event with the operator identity, the item identity, the classification, and the rationale.

Replay must be rate-limited. A burst replay from a large DLQ can overload the downstream system that originally rejected the items. Triage limits replay concurrency per downstream target and paces replays so that the downstream has time to absorb them. The rate-limit propagation article in this family describes the corresponding mechanism on the agent side.

Quarantine items that exhibit suspicious patterns. A DLQ item whose payload contains content that resembles injection, an item whose failure pattern correlates with a known attack campaign, or an item whose sender identity has been flagged requires separate handling. Quarantine freezes replay until security review clears the item; the quarantine decision is itself a policy-violation subclass and feeds the security telemetry.

Define and enforce a maximum DLQ age. Items that exceed the maximum age are routed to cold storage with a `stale-dead-letter` marker and removed from the active queue. The maximum age is operation-specific but should be conservative; an item that has been waiting for triage for months is unlikely to be safely replayable without re-validation.

## Validation evidence

Conformance tests must cover: correct classification of canonical failure modes for each of the four classes, idempotent replay that produces no duplicate side effects, bounded re-injection counts, parking and bulk replay after a fix, archival of permanent failures with full context, security review routing for policy violations, rate-limited replay under load, and quarantine of suspicious items. Inject simulated DLQ items for each failure mode and verify the triage decision matches the documented class.

Operational evidence includes: DLQ depth over time, distribution of items across the four triage classes, mean time to triage, mean time to replay, replay success rate, count of quarantine escalations, and the count of items exceeding maximum age. Reviewers should be able to trace any replayed item from DLQ arrival through triage decision to successful downstream processing.

## Failure handling

When the triage process itself fails — for example, when the operator UI is unavailable or when the audit pipeline is down — DLQ items continue to arrive but cannot be processed. The agent runtime must continue to accept and store DLQ items durably so that they are not lost. Triage resumes when the failure is resolved, and operators must confirm that no items were dropped during the outage.

When a replay causes a downstream failure that is worse than the original (for example, when the downstream has changed since the original attempt), the triage process must immediately stop replay, escalate the affected items to a higher-priority review queue, and notify the operator. Auto-replay must not proceed after a worsening signal; the decision to continue requires a human review.

When a permanent-failure item is later determined to be replayable (for example, a malformed input whose parser has been fixed), the item is promoted from cold storage to the active queue and replayed under the same triage controls as a fresh item. Promotion is itself an audit-recorded action.

## Canonical sources

- NIST SP 800-53 Rev. 5, SC-36 Distributed Processing and Storage (background reference for handling items that cannot be delivered): https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- OWASP Top 10 for LLM Applications (background reference for prompt injection and related content-triage patterns): https://owasp.org/www-project-top-10-for-large-language-model-applications/
- IETF RFC 9325, Recommendations for Secure Use of TLS and DTLS (background reference for replay protection on transport): https://www.rfc-editor.org/rfc/rfc9325
- ISO/IEC 27035-1:2023, Information security incident management (background reference for incident triage discipline): https://www.iso.org/standard/78973.html
