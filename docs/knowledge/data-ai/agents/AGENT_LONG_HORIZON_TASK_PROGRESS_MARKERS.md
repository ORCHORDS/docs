# Long-Horizon Task Progress Markers Under the MCP Tasks Extension

## Scope

Long-horizon agent work - multi-step plans that span minutes, hours, or that suspend for human review - demands an externalization of state. The model context cannot be trusted to persist across sessions, model version changes, or platform restarts. Progress markers are the artifact that make long work auditable, resumable, and honest with users. The MCP Tasks extension formalizes progress semantics for such work, defining the lifecycle states, the events emitted at transitions, and the contract by which a client can resume after disconnect.

This article covers the governance of progress markers under the MCP Tasks extension, with a focus on state semantics rather than protocol mechanics. The extension has opinions about what a task is and is not; aligning agent implementations with those opinions is what makes interoperability durable.

## Workflow or implementation guidance

1. Externalize every long-running agent task as a Tasks object from the moment the run begins, not when it first appears to be taking long. The protocol is cheap; an externalized task that completes quickly is a non-event, while an externalized task that never appears makes incident response guess at state.
2. Define progress units in domain terms, not in token terms. A step is "retrieved candidate records," not "spent 2000 tokens." Domain units are interpretable by clients, customers, and auditors; token counts are not. Where internal steps must be reported, label them with their purpose.
3. Emit transitions for the states the MCP extension defines, and do not invent intermediate states without naming and reviewing them. Inventing states makes cross-tool correlation difficult and quietly re-creates the protocol on top of the protocol.
4. Carry enough context in the task record to resume without re-derivation. Resumption should not depend on the original model, the original prompt revision, or the original tool set being identical to the run that started. Where they are required, mark them required and verify them at resume.
5. Update progress markers on a cadence and a trigger set, not continuously. Continuous updates saturate observers and obscure meaningful transitions. Trigger updates on step completion, retry, escalation, and externally meaningful milestones.
6. Make pause and resume first-class, not exceptional. Long-horizon work frequently pauses for human approval, rate-limit windows, or downstream availability. The task model must represent paused state with a clear resume path; treating pause as a failure makes operators avoid it.
7. When a task is canceled, record cancellation as an event with a reason code and an originating actor. Canceled is not the same as failed, and conflating them distorts success metrics and incident timelines.
8. Allow a task to be reattached by an authorized identity other than its creator, with explicit reattachment evidence. Long-horizon work often needs to be picked up after the original operator is unavailable, and the inability to reattach creates unrecoverable stalls.

## Controls

Authorization for task mutation is a control, not a metadata field. Pause, resume, cancel, and reattach must each be authorized individually, with audit entries carrying the actor and reason. A model that initiated a task is not automatically authorized to cancel it on its own; explicit human or policy authorization must intervene for consequential state changes.

Idempotency on resume prevents the most expensive kind of duplicate work. Each task action should be assignable an idempotency key tied to the task state at action time, so retries during disconnection do not double-execute downstream effects. Without idempotency, every retry is a potential regression.

Progress markers are evidence. Retain task state transitions with timestamps, actor identifiers, and reason codes for an incident-relevant window. Treat marker records as the primary truth about a task's existence; secondary data sources are corroboration. When records diverge, the markers take precedence and the divergence is investigated.

## Validation evidence

Demonstrate the full lifecycle on a representative long-horizon task: created, advanced through planned steps, paused for human review, resumed by a different authorized identity, and completed. Each transition should emit the corresponding event and be reflected in the marker record with the actor and timestamp.

Test resumption under conditions that occur in practice: model restart, client disconnect, network partition, and tool availability fluctuation. Verify that resumption after each uses the same idempotency record and produces the same downstream effect on retry, or that divergence is detected and reported. Test unauthorized reattachment: an actor without reattachment rights is refused, and the refused attempt is logged with sufficient detail to investigate.

Show that progress markers survive model and prompt revisions. A task in progress at revision time should resume correctly using the same markers, not require new artifacts and not silently lose history. Show that cancellation is distinct from failure in reporting and that operator dashboards reflect the distinction correctly.

## Failure modes and correction

A frequent failure is progress markers that report only the optimistic case. A marker that advances on completion but never records a stall, a retry storm, or a partial result gives operators a misleading view. Correct by emitting markers on every state transition the protocol defines, including the failure-oriented ones.

A subtler failure is reattachment without authorization. Once a task is externalized, any actor that can reach the task object can in principle mutate it. Correct by binding task authorization to a principal and verifying at every mutating call, and by tracking principal continuity across resumption.

Another failure is treating markers as decorative. Operators view progress markers as the operational reality; treating them as cosmetic causes the operational reality to drift from what the system actually did. Correct by aligning markers with state transitions as defined and by reviewing markers as a control on a defined cadence.

## Limitations

The MCP Tasks extension's progress model assumes a particular definition of state transition semantics that may not fit every workflow, especially workflows with continuous state rather than discrete steps. Long-horizon work also depends on the durability of the underlying task store; a store that loses records causes the marker scheme to lose truth. Marker storage scales with task volume, and aggressive summarization risks recreating the lost-detail problem the markers were meant to prevent.

## Canonical sources

- **Model Context Protocol, Tasks extension overview:** https://modelcontextprotocol.io/extensions/tasks/overview
- **Model Context Protocol, Tasks extension specification (markdown form):** https://modelcontextprotocol.io/extensions/tasks/overview.md
- **Model Context Protocol, extensions index:** https://modelcontextprotocol.io/extensions/overview
