# Capability Revocation During Long-Running Agent Tasks

## Scope

A long-running agent may be admitted while a user, service account, tool, or resource permission is valid, then continue after that authority is revoked. Checking only at task creation leaves a gap between authorization and effect. This article defines revocation-aware execution for capabilities and delegated authority. It complements least privilege and policy decisions but focuses on validity over time, including queued and resumed work.

OWASP authorization guidance calls for validation on every request and deny-by-default behavior. NIST SP 800-53 includes account management, access enforcement, session termination, and revocation objectives. OAuth token revocation defines a standard revocation endpoint for certain tokens, but agent applications must still decide how revocation reaches leases, caches, queues, and derived child authority.

## Workflow

1. At admission, resolve subject, tenant, resource, action, delegation chain, credential or decision identifier, policy revision, and revocation generation.
2. Issue a short-lived internal capability scoped to the exact operations, resources, audience, and run. Children receive narrower capabilities with an expiry no later than the parent.
3. Before every side effect and at defined checkpoints for reads, validate expiry, audience, scope, run state, and current revocation generation. Do not rely on the model to remember this check.
4. Subscribe to or poll an authoritative revocation source. Events carry monotonically advancing subject, resource, policy, or credential generations and are applied idempotently.
5. On revocation, prevent new operations, cancel queued calls, stop lease renewal, fence late results, and transition the run to `authorization_revoked` or a narrower permitted mode.
6. Reauthorize any continuation or resume against current state. A checkpoint preserves progress, not authority.
7. Invalidate authorization caches by generation rather than waiting only for time-to-live. Bound any unavoidable propagation window and document it.
8. Close child capabilities and temporary credentials at terminal task state even if their nominal expiry is later.

## Controls, data, and evidence

Capabilities should be unforgeable references or integrity-protected assertions with minimal claims. Bind them to an audience so a token for one tool cannot be replayed at another. Keep revocation generation in strongly controlled state and make rollback impossible. Use separate generations when revoking one resource should not terminate unrelated work.

Record capability ID or digest, parent capability, scopes, audience, issue and expiry, policy revision, generation at check, checkpoint checks, revocation event revision, cancellation outcome, and any side effects committed before and after receipt. Do not store bearer values. Evidence includes access reviews, propagation-latency measurements, cache invalidation tests, resumed-task tests, and reconciliation proving no accepted commits used a stale generation after the enforcement boundary learned of revocation.

## Validation tests

Revoke the subject while a task is queued; it must never dispatch. Revoke during an external call and verify a late response cannot trigger another action. Resume an old checkpoint after revocation and confirm fresh authorization fails. Revoke only one resource and ensure unrelated explicitly scoped work follows policy rather than broad accidental termination.

Delay, duplicate, and reorder revocation events; monotonic generation handling must converge without rollback. Partition a worker from the revocation channel until its maximum validity window expires. Attempt to use a child capability after its parent is revoked, against another audience, or beyond the parent's expiry. Change a role while an authorization cache entry is live and verify the generation invalidates it. Measure the maximum time from authoritative revocation to blocked commit under load.

## Failure handling

If the revocation service is unreachable, do not extend capabilities. Continue only until the short validity boundary under an explicitly approved policy; high-impact side effects may require online confirmation and fail immediately. If generation state moves backward or conflicts, treat authorization as indeterminate and stop affected operations.

When a stale capability appears to have committed after revocation became enforceable, isolate the resource, terminate descendants, reconcile side effects, and apply domain-specific compensation. Distinguish unavoidable propagation latency from a failed check, but document both. Recovery requires fresh issuance, not reactivation of the revoked capability. Revocation events themselves must not carry arbitrary commands.

## Limitations

Immediate revocation is impossible across a partitioned distributed system without sacrificing availability. Short lifetimes reduce exposure but increase dependency load. External systems may accept an already-started action despite local cancellation. Generation granularity trades targeted revocation against state complexity. Revocation does not undo completed effects and cannot fix excessive scopes that remain valid. Token-revocation protocols also do not automatically revoke application sessions, cached decisions, or derived credentials unless those links are explicitly enforced.

## Canonical sources

- **OWASP, Authorization Cheat Sheet:** https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- **NIST, SP 800-53 Revision 5:** https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- **IETF, OAuth 2.0 Token Revocation (RFC 7009):** https://www.rfc-editor.org/rfc/rfc7009.html
