# Transactional Outbox for Agent Side Effects

## Scope

An agent often needs to update durable state and request an external side effect. If it commits state and crashes before sending, work is lost; if it sends first and crashes before recording success, a retry may duplicate the action. A transactional outbox writes the intent and local state in one transaction, then a separate dispatcher delivers it. This article covers that reliability boundary and does not claim distributed exactly-once execution.

NIST SP 800-53 addresses information integrity, transaction recovery, audit, and contingency objectives. HTTP semantics defines idempotent methods but application operations frequently require their own idempotency keys. The outbox pattern combines atomic local commitment with at-least-once delivery and explicit destination deduplication.

## Workflow

1. After authorization and validation, create a canonical side-effect command with destination, operation type, constrained parameters, authorization context reference, idempotency key, and expiry.
2. In one database transaction, apply the local state transition and insert an immutable outbox row. If either write fails, commit neither.
3. A dispatcher claims rows using a lease and fencing token. It marks ownership without making the business action appear complete.
4. Before delivery, recheck expiry and any policy that must be current at execution time. Some approvals can authorize a fixed command; others require fresh state.
5. Send the command with its stable idempotency key and bounded deadline. The destination records that key atomically with its own effect whenever possible.
6. Record the acknowledged destination result. Duplicate acknowledgements update no business effect.
7. Retry transient delivery failures under a bounded policy. Classify permanent validation, authorization, and semantic failures for review or compensation rather than endless retries.
8. Mark the workflow complete only when the defined acknowledgement condition is satisfied. Retain the outbox evidence for the required period, then archive or delete safely.

## Controls, data, and evidence

The outbox table belongs in the same transactional resource as the local state it protects. Restrict insertable operation types and destinations; never store arbitrary executable instructions. Encrypt sensitive parameters or store references. Dispatcher identities receive only claim, read-approved-command, and delivery-result privileges. Apply queue ceilings and partitioning to prevent one destination from blocking all others.

Store outbox ID, business aggregate and revision, command digest, destination, operation, idempotency key, policy and approval references, creation and expiry, claim token, attempt count, last classified error, acknowledgement digest, and terminal status. Evidence includes transaction tests, destination deduplication contracts, retry classification, reconciliation reports, stuck-row alerts, and samples tying local state to one immutable command.

## Validation tests

Crash immediately before and after the database commit; observe either neither record or both local state and outbox row. Crash after destination success but before acknowledgement storage; redelivery must not duplicate the effect. Deliver the same row concurrently from two dispatchers and verify fencing plus destination idempotency.

Return transient, permanent, malformed, and ambiguous responses. Only approved transient classes retry automatically. Expire a queued command and ensure it is not sent. Revoke authorization under both defined models—fixed authorization and execution-time authorization—and verify their documented differences. Modify a claimed row and confirm immutable digest checks fail. Reconcile destination records against outbox rows and identify missing, duplicate, and unknown effects.

## Failure handling

If the dispatcher is down, committed rows remain pending and visible through age alerts; local status must say pending, not complete. If acknowledgement is ambiguous, retry only when the destination supports the same idempotency key or escalate for reconciliation. Creating a new key turns uncertainty into duplicate risk.

For permanent failure, mark the row terminal and transition the business aggregate to a truthful failed or intervention-required state. Compensation is a new authorized command, not deletion of history. If the outbox store is corrupt, stop dispatch, restore from a consistent backup, and reconcile with destinations before resuming. Dead-letter storage must remain bounded and retain enough metadata to act safely.

## Limitations

The pattern guarantees atomicity only inside the local transaction. Without destination deduplication, delivery remains at least once and can duplicate effects. Some real-world actions cannot be reversed or queried reliably. Long outages can make commands stale even before explicit expiry. Ordering across multiple aggregates or destinations requires additional design. The outbox also adds latency and operational storage, and it cannot correct an authorized but semantically wrong command.

## Canonical sources

- **NIST, SP 800-53 Revision 5:** https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- **IETF, HTTP Semantics, Idempotent Methods (RFC 9110):** https://www.rfc-editor.org/rfc/rfc9110.html
- **NIST, SP 800-34 Revision 1, Contingency Planning Guide:** https://csrc.nist.gov/pubs/sp/800/34/r1/final
