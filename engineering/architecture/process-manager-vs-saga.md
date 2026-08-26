# process-manager-vs-saga

**Issue:** Teams building event-driven systems routinely conflate the Saga pattern with the Process Manager pattern because both coordinate work that spans multiple services and both outlive a single request. The confusion is not academic: it changes where state lives, how failures are compensated, who is allowed to make routing decisions, and what the code looks like when the tenth step of a workflow fails at 3 AM. A saga, in its classical form, is a sequence of local transactions with compensating actions, and the coordination logic itself may be distributed across participants. A process manager is a stateful central component that maintains the state of a long-running process as an explicit state machine, decides the next step based on both incoming events and accumulated process state, and can start, stop, and reroute work. Choosing the wrong abstraction produces either a god-orchestrator that owns business logic it should not, or a chain of choreographed services where nobody can answer "what step is this order on." Research from event-driven.io and the EventSourcingDB blog (2026) crystallizes the distinction: the saga itself has no state, while the process manager can be modeled as a state machine that holds the map of the entire journey.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Core Distinction

1. **Saga is a transaction-composition pattern.** A saga breaks a distributed transaction into local transactions, each with a compensating action that semantically undoes it if a later step fails. Its concern is atomicity-without-locks: how to roll back a business operation that already committed in some services. It prescribes no particular coordinator.
2. **Process manager is a routing-and-state pattern.** A process manager receives events, updates a durable process state (a finite state machine), and emits commands to drive the next step. It is an active participant that holds the map of the entire journey, per the EventSourcingDB 2026 writeup, rather than a passive sequence of handlers.
3. **State placement differs.** In choreography-style sagas, process state is passed along with messages or recomputed by each participant; in a process manager, state is centralized and queryable ("what step is this claim on?"). Centralized state is the practical reason most teams end up adopting a process manager once workflows exceed three or four steps.
4. **Compensation is native to sagas, incidental to process managers.** A process manager can certainly invoke compensations, but it can also retry, branch, escalate to a human, or abandon a process — outcomes outside the saga's compensating-transaction vocabulary. Conversely, a pure saga has no concept of a decision node that waits a week for a manager approval.

## When to Use Which

1. **Use choreographed sagas for short, linear flows.** Two to four steps with obvious compensations (reserve stock, charge card, release stock on failure) work well as choreography: no coordinator to deploy, no additional bottleneck, and the coupling stays within the event contracts.
2. **Use a process manager when branching depends on accumulated state.** If the next command depends on a combination of prior outcomes (credit check result, customer tier, prior incident history) rather than the last event alone, the state-machine decision point of a process manager is the right home for that logic.
3. **Use a process manager when humans or timers participate.** Approval steps, SLA-based escalations, and wait-for-external-callback states are natural state-machine states and awkward to express as saga steps, which assume forward progress or compensation.
4. **Use a process manager when operations needs visibility.** Because the manager owns process state, it can expose dashboards, replay stuck processes, and answer support queries. Choreography hides process position across services and log correlation becomes the only source of truth.
5. **Prefer neither when a single database transaction suffices.** If the steps can live inside one service and one transactional boundary, introducing either pattern is accidental complexity. Both patterns exist to solve the multi-service boundary problem.

## Implementation Approaches

1. **Durable workflow engines.** Temporal, AWS Step Functions, Azure Durable Functions, and Camunda are process managers in product form: durable state, timers, retries, and versioned workflow definitions. Building a bespoke manager is justified only when the engine's operational model does not fit (embedded libraries, unusual runtimes, extreme scale).
2. **Event-sourced process state.** A common custom design persists the process manager's state as a stream of events (process started, step completed, compensation triggered) in the same store used for domain events, so process state is replayable and auditable alongside business data.
3. **Saga orchestrator as a specialization.** Event-driven.io's framing is useful for reviews: a "saga orchestrator" is a process manager specialized for saga coordination. When reviewing code, check that the orchestrator routes and compensates but does not silently absorb domain logic that belongs in services.
4. **Command/event contract discipline.** The manager emits commands (do this) and consumes events (this happened). Keeping the direction explicit prevents the manager from becoming a synchronous RPC hub, which reintroduces the temporal coupling the pattern was adopted to remove.

## Failure and Recovery Semantics

1. **Define the failure vocabulary up front.** Saga thinking pushes you to enumerate compensations per step; process-manager thinking pushes you to enumerate non-happy terminal states (abandoned, timed out, escalated). Do both: every forward command needs a compensation or an explicit decision that compensation is unnecessary.
2. **Make every handler idempotent.** The manager may crash between persisting state and emitting a command, or between emitting and persisting. Durable engines solve this with event-history replay; custom implementations need idempotency keys and at-least-once consumers to be safe.
3. **Persist state transitions atomically with side effects via an outbox.** A custom process manager that updates a database row and then publishes a command is a dual-write bug. Use the transactional outbox so process state and outbound commands commit together.
4. **Bound retry budgets per step.** A process manager that retries a failing downstream step forever converts a transient outage into an unbounded pile of in-flight processes. Cap retries, then transition to a parked/escalated state a human can act on.
5. **Version process definitions defensively.** Long-running processes outlive deployments. New code must be able to load old process states: keep state machine versions backward compatible, or provide migration for in-flight instances before deploying the new version.

## Common Pitfalls

1. **God orchestrator.** The manager accretes business rules until services are dumb CRUD shells and every change touches the coordinator. Keep the manager routing-only; business decisions stay in the services that own the data.
2. **Terminology drift in the codebase.** Teams name classes "Saga" while implementing state machines, which misleads new engineers about failure semantics. Pick the term that matches the actual behavior and document the choice in the module README.
3. **Unobservable choreography.** When choreography is chosen, the absence of central state means nobody can list in-flight sagas. Compensate with correlation IDs in every event and a process view rebuilt from the event log.
4. **Compensation that is not actually compensating.** A refund is a compensation; "mark order as failed" is a state change, not an undo. Audit each compensation to confirm it restores invariants that other services may have already read and acted upon.
