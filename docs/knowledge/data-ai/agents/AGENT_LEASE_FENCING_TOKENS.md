# Lease Fencing Tokens for Durable Agent Workers

## Scope

A lease lets a worker act for a limited period, but expiry alone cannot stop a paused or partitioned worker from resuming and committing stale work. Fencing tokens solve this by giving every new lease acquisition a strictly increasing generation that the protected resource rejects when stale. This article covers durable agent ownership and commit safety. It differs from checkpoint/resume and scheduling: those recover progress, while fencing prevents two generations from both taking effect.

NIST SP 800-53 supplies concurrency, integrity, least-privilege, and fail-safe control objectives. HTTP conditional requests demonstrate the general principle of applying a state precondition atomically. No general standard makes distributed leases perfectly safe; the storage or side-effect boundary must enforce the token.

## Workflow

1. Define the protected scope: task, artifact, account operation, or resource partition. The scope must match the boundary that can reject stale writes.
2. Acquire ownership through an atomic transaction that increments a durable generation and returns `(scope, owner, token, expiry)`.
3. Include the token on every state transition and side-effect request. Intermediaries must not drop or replace it.
4. The destination atomically compares the submitted token with the highest accepted token for that scope. It rejects lower tokens before applying changes.
5. Renewing the same lease may extend expiry without changing generation only when ownership is unquestionably continuous. Reacquisition after loss increments the token.
6. If a worker cannot renew before a conservative deadline, it stops starting operations. It may save local diagnostics but cannot commit protected state.
7. A successor loads the last committed checkpoint, acquires a higher token, and resumes idempotently.
8. Completion atomically records terminal state under the current token and releases or closes ownership so no further transitions are accepted.

## Controls, data, and evidence

Generate tokens in a strongly consistent store with atomic increment or compare-and-swap semantics. Tokens must be scoped, nonwrapping for the system lifetime, and treated as ordering values rather than secrets. Authorization still validates who may acquire and use a lease. Bind tokens to operation identifiers to support idempotency.

Persist acquisition revision, scope, owner, token, issue and expiry times, renewal outcomes, checkpoint revision, attempted commits, rejection reason, and terminal release. Use monotonic time for a worker's renewal scheduling, while the authority decides expiry. Evidence includes storage transaction definitions, downstream enforcement tests, pause-and-resume chaos results, overflow analysis, and an inventory proving every consequential destination checks fencing.

## Validation tests

Pause worker A after it acquires token 10. Let its lease expire, start worker B with token 11, then resume A; all A commits must be rejected. Deliver A's messages after B completes and verify the terminal state remains unchanged. Duplicate B's commit with the same operation ID and confirm idempotent behavior.

Partition A from the lease store but not from the destination. It must stop at the renewal safety point, and the destination must independently reject stale token 10 after token 11 is established. Test concurrent acquisition, transaction retry, process restart, token serialization across languages, and maximum values. Attempt to use a valid token for another scope. Verify every tool adapter either forwards and enforces fencing or is classified unsuitable for recoverable side effects.

## Failure handling

If the lease authority is unavailable, do not issue new ownership. A current worker may continue only within the documented lease and safety margin, provided destinations still enforce its token. If the destination cannot verify tokens, stop protected side effects; local lease confidence is insufficient.

If a stale commit is accepted, isolate the resource, halt both generations, reconstruct order from authoritative state revisions, and apply domain-specific compensation only after review. Never simply choose the latest wall-clock timestamp. If tokens approach representation limits, migrate to a larger generation space before wraparound. Lost ownership should produce a stable `stale_lease` result and terminate the worker's commit path.

## Limitations

Fencing requires cooperation from every side-effect destination. Many third-party APIs cannot compare a caller's generation, so an internal transactional outbox or single writer may be necessary. Tokens order lease generations but do not prove payload correctness. Cross-resource atomicity remains unsolved if one action spans systems. A strongly consistent allocator can reduce availability, and incorrect scope design can leave overlapping writers despite valid tokens.

## Canonical sources

- **NIST, SP 800-53 Revision 5:** https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- **IETF, HTTP Semantics, Conditional Requests (RFC 9110):** https://www.rfc-editor.org/rfc/rfc9110.html
- **IETF, HTTP Conditional Requests (RFC 7232):** https://www.rfc-editor.org/rfc/rfc7232.html
