# Resource-Exhaustion Controls for Tool-Using Agents

## Scope

An agent can consume model tokens, wall-clock time, tool requests, database capacity, queue slots, memory, and money while pursuing one apparently small task. This article addresses deterministic resource governance around an agent run. It is distinct from retry policy, queue backpressure, and timeout propagation: those mechanisms remain useful, but a resource governor decides how much aggregate work a principal may cause across planning, delegation, retries, and tools. Availability and cost are the protected properties.

The OWASP denial-of-service guidance treats resource exhaustion as an application-security concern, while NIST SP 800-53 supplies control families for capacity, boundary protection, monitoring, and least functionality. Neither source defines an agent architecture. The design below applies their control objectives without claiming formal conformance.

## Workflow

1. At admission, resolve the authenticated tenant, user, workload class, and requested service level. Reject requests whose identity or accounting owner is missing.
2. Create a run budget containing maximum elapsed time, model input and output units, tool invocations, concurrent branches, bytes read and written, and monetary exposure. Record the policy revision that produced it.
3. Reserve scarce capacity before execution. A reservation prevents many accepted runs from simultaneously assuming the same remaining capacity. Expire abandoned reservations.
4. Charge every operation to both the run and its principal. Delegated child runs inherit a bounded slice; they never receive a fresh independent allowance.
5. Check remaining budget before an operation, not only afterward. Use conservative estimates for operations with uncertain cost and reconcile estimates with actual usage.
6. When a soft threshold is reached, reduce fan-out, shorten optional context, choose a cheaper approved path, or request a narrower task. Do not silently lower safety checks.
7. At a hard threshold, stop scheduling work, cancel cancellable operations, fence late results, and produce a stable `resource_limit` outcome with safe partial artifacts clearly marked incomplete.
8. Release reservations and finalize accounting even when the run crashes.

## Controls, data, and evidence

Keep limits in versioned policy rather than prompts. Enforce them in the orchestrator and tool gateway, where model text cannot alter counters. Use monotonic clocks for elapsed time. Make counter updates atomic, and attach a unique charge identifier so retransmission cannot double-charge. Principal-wide quotas need a strongly consistent decision point or intentionally conservative regional allocations.

A budget record should contain run ID, principal ID, workload class, limits, reservations, cumulative charges by resource, child allocations, threshold events, termination reason, policy revision, and timestamps. Avoid storing prompt or tool payloads merely to prove accounting. Evidence includes approved capacity assumptions, load-test reports, policy reviews, quota-change records, counter reconciliation, and samples showing that child work is charged to its parent.

Alert on sustained rejection rate, reservation leakage, usage that is not attributable to a principal, reconciliation drift, repeated near-limit runs, and unusually high amplification from one input to downstream operations. Capacity dashboards must separate demand denied at admission from work accepted and later curtailed.

## Validation tests

Run a branching test in which each child attempts to create more children; verify the total never exceeds the parent's concurrency and invocation limits. Inject retries and duplicated completion messages; each operation must be charged once. Crash the worker after reservation and verify lease expiry or recovery releases capacity. Make a tool understate its predicted response size and confirm post-operation reconciliation cannot make limits negative or authorize further work.

Test simultaneous requests from one tenant against the principal-wide quota. Verify an abusive tenant cannot consume another tenant's reserved share. Advance wall time while freezing a process and confirm the monotonic deadline still expires. Exercise integer boundaries and very large declared sizes. Confirm soft degradation preserves mandatory authorization, validation, and output controls. Finally, compare gateway counters with provider bills and infrastructure metrics for a bounded test interval.

## Failure handling

If the accounting service is unavailable, fail closed for expensive or side-effecting work. A narrowly defined low-cost read-only class may use a small local emergency allowance if policy explicitly permits it. Mark those charges for reconciliation. Never interpret inability to read a quota as unlimited capacity.

If cancellation cannot stop an external operation, mark its reservation committed until a result or expiry is known, fence its late response, and prevent it from triggering subsequent work. If reconciliation shows systematic undercounting, reduce admission limits, pause high-amplification workloads, and investigate before restoring normal capacity. Communicate limit failures as operational outcomes, not as fabricated task success.

## Limitations

Quotas cannot prove that a completed action was useful, safe, or fairly allocated. Cost estimates can lag provider pricing and tool behavior. Distributed enforcement trades availability, utilization, and strictness; document that choice. Tight limits may disproportionately affect long but legitimate accessibility or analysis tasks, so workload classes and exception review require evidence. Resource governance also does not replace infrastructure autoscaling, dependency rate limits, or business-level abuse detection.

## Canonical sources

- **OWASP, Denial of Service Cheat Sheet:** https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html
- **NIST, SP 800-53 Revision 5:** https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- **IETF, RateLimit Fields for HTTP (RFC 9333):** https://www.rfc-editor.org/rfc/rfc9333.html
