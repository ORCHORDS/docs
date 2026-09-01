# Compensating Transaction Pattern Saga Orchestration

## Scope

This article covers compensating transactions within orchestrated sagas: long-lived business transactions spanning multiple services, coordinated by a central orchestrator, where each forward action is paired with a semantically inverse compensating action executed on failure. Scope includes compensation pair design, orchestrator-driven rollback sequencing, forward recovery versus backward recovery, and the bookkeeping that makes a partially completed saga observable and resumable. It assumes each step's work is not ACID-composable with the others — otherwise a distributed transaction would be the correct answer. It excludes choreographed sagas (event-driven, no central coordinator) and excludes pure idempotent retry, which is forward recovery without compensation semantics.

## Workflow or implementation guidance

Design compensation pairs before writing the forward steps. For each forward action, answer four questions in order: what does compensation undo semantically (not technically), is it always possible, what is its cost, and can it fail? A charge can be refunded; an email cannot be un-sent — the compensation is a follow-up message, not a reversal. Steps whose compensation is impossible or merely notional must be ordered last in the saga, after all compensable steps, because they represent the point of no return. This ordering discipline — compensable steps first, non-compensable steps last — is the single highest-leverage design decision in the pattern.

Model the orchestrator as an explicit state machine persisted outside the process:

```ts
interface SagaState {
  sagaId: string;
  definition: string;          // saga type + version
  currentStep: number;
  completed: CompletedStep[];  // forward results needed by compensations
  status: 'running' | 'compensating' | 'completed' | 'failed';
}
```

Each forward step records what its compensation will need — the payment id for a later refund, the provisioned resource id for a later teardown — in `completed` before the step is marked done. On failure, the orchestrator walks `completed` in reverse, executing compensations in opposite order, each itself idempotent and retried independently. Compensations must be semantically canceling but operationally independent: a refund does not restore the exact pre-charge balance in a world where other transactions intervened; it applies a canceling delta. Document that distinction for every pair, because "undo" invites the wrong mental model and wrong implementations.

Distinguish recovery policies per failure class. Transient infrastructural failure of a forward step: retry with backoff, no compensation. Business-rule rejection: backward recovery, compensate. Ambiguous outcome (timeout after the request may have applied): resolve first by querying the step's actual state, then compensate or continue — never compensate blindly over an ambiguous result, or you will refund charges that never happened. Forward recovery — retrying the whole saga from the point of failure after fixing the cause — is often cheaper than compensation for saga types whose steps are all idempotent and whose business semantics tolerate delay; make that an explicit choice per saga definition, not an improvisation during an incident.

## Controls

Every saga definition needs a machine-readable contract listing its steps, each step's compensability class (compensable, pivot, retryable-only), and its ordering constraints — reviewed like a schema change, because a step inserted before a pivot silently changes the failure semantics of everything after it. Require a compensation rehearsal for every new compensable step: a test that executes the forward step then its compensation against real dependencies and asserts the externally observable end state is business-equivalent to never having run. Track three gauges per saga type in production: in-flight count, median and p99 saga duration, and compensation rate; a compensation rate above a threshold is a defect signal about the forward steps, not the compensations. Bound saga duration with an explicit timeout that triggers compensation, because an indefinitely running saga holds business-level locks and customer expectations hostage. Persist the orchestrator state transitionally with each step's outcome, and forbid orchestrator logic that depends on in-memory state surviving between steps.

## Validation evidence

Validation is fault-injection against the state machine. Inject a failure at each step position in a test saga of N steps and assert, for each position, that compensation executed in exact reverse order, that the set of compensations equals the set of completed compensable steps, and that the final saga status is terminal. Verify semantic rollback with business-level assertions — after compensate, the account balance, resource inventory, and notification state are equivalent to pre-saga within documented tolerance — not with internal flag checks. Ambiguity drill: force a timeout exactly at the moment a step's side effect applies, and assert the resolution path queries before compensating. Resume drill: kill the orchestrator mid-saga, restart it, and assert the saga continues from persisted state without re-executing completed steps (idempotency proof) and without skipping them (progress proof). Production evidence: a periodically replayed sample of compensated sagas from live logs through a verification query confirming end-state equivalence, since compensation code paths decay fastest precisely because they run rarely.

## Failure modes and correction

The classic failure is the non-semantic compensation: compensation implemented as a technical reversal (restore a database row snapshot) that ignores intervening business activity, producing corrupted balances or resurrected records. Correct by implementing compensations as forward business operations — refunds, cancellations, contra-entries — and asserting business equivalence in tests. The second is compensation failure during rollback: a compensating step itself errors, the orchestrator abandons the rollback, and the saga is stuck half-compensated with no owner. Correct by treating compensations as retriable idempotent operations with their own retry policy, plus an escalation path — a dead-letter state with an alert — when a compensation exhausts retries. The third is the ambiguous-outcome double compensation described above: compensating a charge that never applied. Correct by resolving outcome before compensating, and by making forward steps idempotent under the saga id plus step index. A fourth is orchestrator state loss: state held in a process that restarts, losing the completed-steps ledger and with it the ability to compensate. Correct by persisting state transitionally per step in a durable store. A fifth is pivot misplacement: an irreversible step scheduled early, forcing customer-facing remedies for everything after it; correct through contract review, which is why the machine-readable step contract is a control and not documentation.

## Limitations

Sagas with compensation trade isolation for availability: intermediate states are externally visible, so customers can observe a booking that later evaporates, and the pattern offers no isolation guarantees — only eventual consistency plus apology logic. Compensation is frequently lossy in business terms — refunds do not return the customer's time — so the pattern manages harm rather than eliminating it, and it cannot compensate informational leakage such as a notification already sent. Orchestrated sagas concentrate failure and evolution pressure in the orchestrator, which becomes a coupling point every participating service must negotiate with. Compensation code is the least exercised path in production systems and therefore the most likely to be broken when finally needed, a risk only rehearsal mitigates. Long-running sagas complicate capacity and dependency management, since compensations reference APIs and schema versions that may have changed by the time they run; version-tolerant compensation payloads are additional design burden. Finally, human-in-the-loop steps (manual approval mid-saga) stretch duration arbitrarily and demand explicit timeout and escalation semantics the pattern does not supply by default.

## Canonical sources

- Garcia-Molina and Salem — Sagas, Proceedings of the 1987 ACM SIGMOD International Conference on Management of Data (the foundational paper on long-lived transactions with compensating transactions).
- Microsoft Azure Architecture Center — Compensating Transaction pattern: https://learn.microsoft.com/en-us/azure/architecture/patterns/compensating-transaction
- Microsoft Azure Architecture Center — Choreography pattern (the coordinated-counterpart trade-off): https://learn.microsoft.com/en-us/azure/architecture/patterns/choreography
- Chris Richardson — microservices.io, Saga pattern: https://microservices.io/patterns/data/saga.html
