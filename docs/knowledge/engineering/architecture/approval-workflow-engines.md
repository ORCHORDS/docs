# approval-workflow-engines

**Issue:** Business processes are rarely pure automation: expense reports need a manager's sign-off, refunds above a threshold need finance, publishing needs legal review, and increasingly, AI agent actions need a human checkpoint before they touch production. Teams keep rebuilding this machinery — a status column, an emails-sent flag, a cron job that escalates on Fridays — and each bespoke version rediscovers the same requirements: durable pause points that can wait days for a human, assignment and delegation of tasks, timeouts with escalation chains, idempotent resume on approval, and an immutable audit log of who approved what and when. Approval workflow engines exist because this is a solved problem class with mature tooling (Camunda and other BPMN engines, Temporal, AWS Step Functions with its human-approval pattern, Azure Durable Functions), but the architecture still has to be designed: where process state lives, how the engine pauses and resumes, how UI and API integrate with tasks, and how the approval log satisfies compliance. The current wave of human-in-the-loop AI agent design (documented by Stack AI and the agent frameworks in 2025-2026) is re-learning these same patterns, which makes the underlying architecture worth writing down once.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Core Building Blocks

1. **Human task as a first-class state.** The process reaches a task node and durably pauses; nothing progresses until a completion signal arrives. In BPMN this is a user task; in Step Functions it is a callback pattern where the workflow pauses with a task token (waitForTaskToken) that an external system — approval UI, email responder, Slack bot — redeems to resume the execution.
2. **Task queue and claim semantics.** Pending approvals land in a task list grouped by candidate group or role (finance team, direct manager). Claiming must be atomic: when two approvers open the same request, exactly one claim wins, and the other sees "already handled" rather than double-approving.
3. **Structured decision outcomes.** An approval completes with a typed result — approve, reject, return-for-changes, delegate — not a free-text comment. The gateway logic after the task branches on these outcomes (BPMN exclusive gateways are the canonical modeling of the approve/reject branch).
4. **Assignment and delegation rules.** Who approves depends on process data: the requester's manager from the org chart, a role lookup for amounts over thresholds, round-robin within a group, or delegation when an approver is on leave. Encode these as resolvable expressions in the process definition, not as hardcoded emails.
5. **Resume idempotency.** The completion signal is a message that can be delivered more than once (double-click, retry). The engine must correlate it to the exact waiting task and ignore duplicates, or an approval counted twice corrupts downstream logic.

## Engine Choices

1. **BPMN engines (Camunda, Flowable, Zeebe).** Full process-modeling notation with user tasks, swimlanes, and gateways; analyst-friendly visual models; mature task list APIs. Best when non-engineers own process definitions or compliance requires formal process documentation.
2. **Durable execution engines (Temporal, Azure Durable Functions, Step Functions).** Approval waits are modeled as activities that can sleep for days; the engine handles durability, timers, and retries. Developers write code instead of diagrams; observability comes from execution history. Temporal's task-queue model in particular maps approvals to workers polling for human-interaction tasks.
3. **Database-backed state machines.** A table of process instances with state, assigned approver, and deadline, plus transition endpoints, is a legitimate small-scale engine. Acceptable up to a few workflow definitions; becomes a liability when timers, escalation, and versioning are bolted on ad hoc.
4. **Embedded approval services for AI agents.** The 2025-2026 human-in-the-loop agent pattern is the same architecture with new clients: the agent pauses before an effectful action and emits an approval request; a human approves via chat, UI, or email; the agent resumes. The durable-pause-plus-callback core is identical, so reuse the same engine rather than building a parallel one for agents.

## State Modeling Rules

1. **Explicit states, explicit transitions.** Enumerate the lifecycle (draft, submitted, awaiting_approval, approved, rejected, escalated, cancelled, expired) and the only-allowed transitions between them. Every transition endpoint validates against this matrix so an invalid hop (approved after cancelled) is a 409, not a silent state overwrite.
2. **Version process definitions.** In-flight instances keep the definition version they started under; new instances use the new one. Deploy mid-process changes (raising a threshold) only with an explicit migration policy for existing instances — engines like Camunda and Temporal have documented migration tooling for exactly this.
3. **Separate process state from business state.** The workflow tracks approval progress; the business document (the expense report) tracks its own fields. Correlate by business key, but never store "amount" in two places or the approval log will disagree with the document it approved.
4. **Model the unhappy paths as first-class flows.** Rejection, return-for-changes (resubmission loop), expiry, and cancellation are not exceptions — they are drawn paths. Processes that only model approval end up implementing rejection as error handling scattered across services.

## Timeout, Escalation, and SLA

1. **Timer boundaries on every human task.** Each task gets a deadline; on expiry the engine fires an escalation boundary event — remind, reassign to a backup approver, escalate to the next level, or auto-approve/auto-reject per policy. Engines provide boundary timers and escalation code lists precisely for this.
2. **Escalation is data, not code paths.** Model escalation chains (manager, then director, then auto-resolve) as configuration the process reads, so policy changes do not require redeploying workflow code.
3. **SLA visibility.** Track per-task age, per-approver queue depth, and deadline breach counts. A workflow engine gives you this nearly for free from execution history; bespoke state columns do not.
4. **Decide auto-resolution policy explicitly.** Auto-approve on timeout is dangerous (silence becomes consent); auto-reject annoys users on approver vacation. Prefer escalation-to-human, and reserve auto-resolution for low-risk, well-instrumented classes.

## Audit and Compliance

1. **Immutable approval log.** Record who claimed, who decided, the decision, timestamp, comments, and the process version — append-only, never editable. Compliance and dispute resolution depend on the log being authoritative; storing it in the same mutable row as process state undermines that.
2. **Segregation of duties.** Enforce that requester and approver differ, and that the same approver cannot hold both roles in multi-stage chains. Encode as validation at task assignment, with any exception (small-team override) logged as an auditable event.
3. **Retain execution history.** Beyond the log of decisions, keep the process trace (which path executed, which boundary timers fired). Reconstructing "why was this refunded without finance review" requires the trace, not just the final state.
4. **PII minimization in notifications.** Approval notifications (email, chat) leak data to whatever channel they render in; keep payloads to references and send details through the authenticated approval UI, with access checks matching the candidate group.
