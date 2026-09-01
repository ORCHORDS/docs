# Command Pattern Audit Log Append Only

## Scope

This article covers the Command pattern — GoF behavioral pattern encapsulating a request as an object — implemented so that the command record itself is the audit log entry, written to an append-only store before the operation takes effect. Scope includes command representation for auditing, the dual-write ordering problem between the audit record and the side effect, replay and forensics over the resulting log, and the relationship between audit logging and event logging. It excludes general application logging, metrics, and tracing, which are operational telemetry rather than evidence, and excludes full event sourcing, where the log is the system of record for state rather than a record of authorized intents.

## Workflow or implementation guidance

Model each command as a self-describing record containing: a command type, a unique command id, the actor identity and auth context at issuance time, the request parameters in a normalized (canonicalized) form, the target resource identifier, the wall-clock issuance time, and a schema version. The discipline that separates an audit log from a debug log is normalization and completeness: write the parameters in the canonical form the authorization decision was made against, not the raw request bytes, so that replaying the decision later is possible.

Order the writes to survive partial failure. Write the audit record durably before performing the side effect, and carry the command id into the side effect's own records so the two can be joined later. Where the side effect and the audit write cannot share a transaction, prefer the order "audit first, then act": a spurious audit record for an action that failed is a mild anomaly an operator can annotate, whereas an action with no audit record is an unaccountable change. Structure it as:

```ts
async function execute(cmd: Command, audit: AuditStore, handler: Handler): Promise<Result> {
  await audit.append({ ...cmd, recordedAt: now(), decision: 'authorized' }); // durable, immutable
  const result = await handler.apply(cmd);           // may fail — annotate, never delete
  await audit.append({ commandId: cmd.id, outcome: summarize(result) });
  return result;
}
```

Append-only must be enforced by mechanism: the store's access policy denies update and delete to the application identity, retention is governed by lifecycle rules the application cannot shorten, and entries carry a hash chain — each record includes the hash of its predecessor — so tampering is detectable even by someone with store access. Keep a distinction between the intent record (what was authorized) and the outcome record (what happened), linked by command id; collapsing them into one write loses exactly the information incident responders need when an authorized action produced an unintended result.

For high-volume paths, batch appends asynchronously but acknowledge commands only after the audit write is confirmed durable; an in-memory buffer that can be lost on crash is not an audit log.

## Controls

The controls are about immutability, completeness, and joinability. Enforce write-only access at the store layer and verify it with a scheduled negative test — attempt an update and delete from the application identity and assert both fail; a permission change that quietly granted update rights would otherwise go unnoticed for years. Track completeness with a reconciliation counter comparing executed side effects against audit entries per time bucket; any nonzero gap means commands are bypassing the instrumented path, which is the single most common audit failure — someone added a direct store write that skipped command encapsulation. Require schema versioning on every entry with a documented evolution policy (new fields optional, removed fields renamed-not-reused), because an audit log outlives the code that wrote it and unreadable history is not evidence. Verify the hash chain periodically — a background job re-computes the chain over recent windows and alerts on any break. Redact secrets by policy at capture time (never log credential fields), but never redact actor identity or timestamps; a log that cannot attribute is decoration.

## Validation evidence

Evidence for this pattern is forensic capability, demonstrated on a schedule. Completeness audit: for a sampled period, join side-effect records to audit entries by command id and report the unmatched rate on both sides — the number must be zero or explained. Immutability test: the negative update/delete probe described above, run in production against the real policy, confirming rejection. Tamper-evidence drill: take a recent window, recompute the hash chain, then (in a copy) mutate one record's payload and confirm the chain verification fails at exactly that entry — proving the detection works, not just that the mechanism exists. Replay exercise: reconstruct the sequence of commands affecting one resource over a past incident window and produce a timeline an investigator can follow without access to source code — this is the deliverable the pattern exists for, and it should be rehearsed before it is needed. Retention check: confirm lifecycle rules match the documented retention policy and that no application credential can shorten them.

## Failure modes and correction

The dominant failure is the unlogged fast path: a hot code path bypasses command encapsulation for performance, and its actions are invisible to audit — usually discovered during an incident when the timeline has holes. Correct by making the store inaccessible except through the command executor and by running the completeness reconciliation regularly rather than annually. The second is the mutable "audit" table: a log implemented as an ordinary database row set gets updated during incident cleanup, destroying the record of what was actually attempted. Correct with append-only enforcement at the policy layer plus the negative probe, and if a cleanup annotation is needed, append a new linked entry rather than editing. The third is actor loss: commands executed by background jobs or on behalf of scheduled triggers carry no actor, and the log fills with `system` entries that attribute nothing. Correct by modeling an explicit service actor with the triggering context (schedule id, initiating user where chained). A fourth is the dual-write gap in the other direction — acting first, logging after — which under crash leaves actions with no record; correct the ordering and reconcile gaps by annotating from side-effect records, never by fabricating backdated entries.

## Limitations

An append-only audit log is write-amplification: every mutation becomes two durable writes minimum, and the log's storage grows without bound absent a retention policy that someone must own and defend against both cost pressure and legal-hold requirements. The pattern records intents and outcomes, not proofs of internal state — an attacker with application-level privilege can write plausibly-formed entries, and only the hash chain and external timestamping raise the bar rather than eliminate the risk. Batching for throughput introduces a loss window that must be acknowledged in the design, since a strict interpretation of audit requirements may forbid it. Reading the log for analytics is awkward by construction — append-only, hash-chained, ordered-by-time stores are poor query subjects, so investigation tooling and projections become necessary secondary investment. Finally, the pattern says nothing about access to the log itself; without separate read governance, the audit trail becomes its own exfiltration surface containing every parameter ever submitted.

## Canonical sources

- Gamma, Helm, Johnson, and Vlissides — Design Patterns: Elements of Reusable Object-Oriented Software, Addison-Wesley, 1994 (Command, Behavioral Patterns catalog).
- Microsoft Azure Architecture Center — Command and Query Responsibility Segregation (CQRS) pattern, including the command-side write model: https://learn.microsoft.com/en-us/azure/architecture/patterns/cqrs
- Cloudflare Queues documentation (durable async append plumbing for command records): https://developers.cloudflare.com/queues/
- Fowler — Event Sourcing (relationship between recorded intents and state reconstruction): https://martinfowler.com/eaaDev/EventSourcing.html
