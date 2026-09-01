# Fail-Safe Modes for Agent Policy Dependencies

## Scope

Agents often depend on authorization, content classification, quota, schema, and safety-policy services. When one is unavailable or returns an indeterminate decision, continuing normally can turn infrastructure failure into unauthorized action. This article defines explicit fail-safe modes and recovery criteria. It differs from circuit breakers, which protect dependency availability; fail-safe design decides what the agent may do after a required policy decision cannot be established.

NIST SP 800-53 includes fail-safe procedures, least privilege, contingency planning, and authorization controls. OWASP authorization guidance recommends deny by default and checking permission on every request. Those principles do not mean every read must disappear during every outage; they require preclassified, bounded behavior whose safety does not depend on an unavailable decision.

## Workflow

1. Inventory policy dependencies for every agent operation and label each as mandatory, advisory, or optional. Treat authorization for side effects as mandatory.
2. Define modes before incidents: normal, restricted read-only, cached-public-data, human-only, drain, and stopped. Specify allowed operations and entry and exit conditions for each.
3. At admission, evaluate required dependencies and select the most restrictive applicable mode. Bind the mode and policy revisions to the run.
4. Before each consequential operation, recheck mandatory decisions according to their validity period. A run admitted in normal mode may transition to a stricter mode but never broaden itself without fresh authoritative evaluation.
5. On timeout, malformed response, conflicting decisions, or unavailable policy service, produce `indeterminate`, not `allow` or `deny` disguised as a transport error.
6. Map `indeterminate` to the operation's preapproved fail-safe behavior. Side effects usually stop; display of independently classified public static help may continue.
7. Cancel or drain work that is no longer permitted, fence late results, and preserve truthful partial status.
8. Exit restricted mode only after health, consistency, and freshness checks succeed for a defined stabilization interval.

## Controls, data, and evidence

Implement enforcement outside the model. Keep an operation-to-dependency matrix and a machine-readable mode capability table under review. Use short validity periods for cached decisions and bind them to subject, resource, action, context, policy revision, and revocation generation. A cached allow must not be generalized to another object or action.

Record mode transitions, triggering dependency, decision category, operation blocked or allowed, cached-decision age, policy and capability-table revisions, stabilization checks, and operator overrides. Do not copy sensitive policy inputs into routine records. Evidence includes failure-mode analysis, tabletop exercises, outage injection, approved public-data classifications, override reviews, and samples showing that model output cannot alter mode.

## Validation tests

Make the authorization service time out during a side-effecting tool call; no action may start. Return malformed, contradictory, or unsigned policy data and verify it becomes indeterminate. Continue a safe public-information request under the designated mode and prove its data source is independent of the failed service. Expire a cached allow and confirm it is not extended by repeated failures.

Transition a running workflow from normal to stopped while children are executing; confirm cancellation and fencing prevent later commits. Restore the dependency intermittently and verify stabilization prevents mode flapping. Attempt an operator override without the required role, justification, or expiry. Restart the orchestrator in restricted mode and confirm it does not assume normal operation from process startup. Test that status messages say incomplete or blocked rather than success.

## Failure handling

If the mode service itself fails, use a compiled restrictive baseline. If the current policy revision cannot be established, prohibit operations requiring it. Emergency overrides must be narrow by operation and tenant, time bounded, independently authorized, and visible; they should never disable evidence collection or fencing.

After recovery, do not automatically replay blocked side effects. Reauthorize them against current state and require idempotency or fresh user confirmation as appropriate. Reconcile tasks that were partially completed, revoke stale leases, and communicate which outputs came from restricted sources. If normal-mode actions occurred during an indeterminate interval, treat that as a control failure and investigate affected resources.

## Limitations

Fail-safe behavior can reduce availability and may itself cause harm in time-sensitive domains. Determining that data is genuinely public and static requires governance. Cached decisions cannot reflect immediate revocation unless a separate generation mechanism is reachable. Human-only mode depends on human capacity and trustworthy interfaces. This pattern cannot compensate for policy logic that incorrectly returns allow, nor can it decide legal or domain obligations without organizational analysis.

## Canonical sources

- **NIST, SP 800-53 Revision 5:** https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- **OWASP, Authorization Cheat Sheet:** https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- **NIST, Cybersecurity Framework 2.0:** https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf
