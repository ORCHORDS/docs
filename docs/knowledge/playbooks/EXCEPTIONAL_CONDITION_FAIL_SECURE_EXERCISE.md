# Exceptional Condition Fail-Secure Exercise

## Trigger
Run before releasing security-sensitive or transactional flows, after material error-handling changes, after incidents involving partial/unknown state, and during resilience/security testing.

## Inputs
- Critical transaction and authorization flows.
- Error/exception-handling design and safe-state expectations.
- Fault-injection or test doubles for dependencies/resources where feasible.
- Observability/logging and reconciliation/rollback mechanisms.

## Procedure
1. Select representative security-sensitive and multi-step flows whose failure could affect confidentiality, integrity, authorization, money/value, or durable state.
2. Define the expected safe state for each selected flow before injecting failures.
3. Exercise missing/invalid input and verify the flow stops at the intended validation boundary.
4. Exercise insufficient-privilege or authorization failures and confirm the system fails closed rather than falling through to a reduced-check path.
5. Inject dependency/network/timeout failures at different stages of multi-step operations and inspect committed state after each fault.
6. Inject resource, null/unexpected-state, or other abnormal conditions appropriate to the implementation and confirm the system enters a documented state.
7. Verify transactions roll back, compensate, or enter an explicit reconciliation state when atomic completion is not possible.
8. Verify public error responses remain controlled while protected telemetry retains enough diagnostic context for investigation.
9. Restart/recover the service where relevant and verify persistent state is consistent rather than assuming restart equals recovery.
10. Record deviations from the expected safe state, remediate, and repeat the same fault at the same stage.

## Escalation
Escalate fail-open authorization behavior, partial state that cannot be reconciled, duplicated or lost value/state, sensitive error disclosure, or faults that leave the application in an unknown security state.

## Evidence
- Selected flow/fault matrix.
- Expected safe-state definitions.
- Fault-injection results.
- Transaction/state verification.
- Public/internal error evidence.
- Recovery/restart verification.
- Findings and retest evidence.

## Completion criteria
Representative exceptional conditions preserve documented security and transaction invariants, with fail-closed behavior and explicit rollback/compensation/reconciliation where required.

## Source basis
- OWASP Top 10:2025 A10 — Mishandling of Exceptional Conditions: https://owasp.org/Top10/2025/A10_2025-Mishandling_of_Exceptional_Conditions/
