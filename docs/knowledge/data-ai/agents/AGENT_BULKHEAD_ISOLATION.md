# Bulkhead Isolation for Multi-Tenant Agent Runtimes

## Scope

A bulkhead limits how much shared execution capacity one workload can occupy. In an agent runtime, isolation may apply to tenants, tools, workload classes, side-effect lanes, model endpoints, or human-review queues. The purpose is to contain saturation and preserve minimum service for unrelated work. This is different from per-run resource budgets and circuit breakers: budgets cap one principal's aggregate use, while bulkheads partition concurrent capacity; breakers react to dependency health.

NIST SP 800-53 includes availability, capacity, boundary, and least-functionality objectives. OWASP denial-of-service guidance emphasizes limiting resources and designing graceful degradation. The following pattern translates those goals into agent scheduling controls without asserting that partitioning alone satisfies either source.

## Workflow

1. Inventory scarce pools: worker slots, outbound connections, model concurrency, database sessions, browser instances, memory, and reviewer capacity.
2. Classify runs at admission using authenticated tenant and approved workload metadata. Never let free-form prompt text select a privileged lane.
3. Assign each class a hard concurrency ceiling, queue ceiling, service weight, and optional reserved minimum. Maintain a small emergency lane only for explicitly defined recovery work.
4. Acquire all required pool permits in a canonical order before starting an operation. If permits are unavailable, wait within the request deadline or reject; do not hold one scarce permit indefinitely while waiting for another.
5. Charge delegated children to the parent's class and tenant. A child cannot escape isolation by changing tool names or spawning a new run.
6. Schedule fairly within each pool, accounting for task size where feasible. Prevent one stream of tiny tasks from permanently starving long approved tasks, and prevent long tasks from monopolizing all workers.
7. Release permits in guaranteed cleanup paths. Detect and reclaim permits from dead workers through leases plus fencing.
8. During overload, shed lowest-priority optional work first while preserving safety checks, state consistency, and truthful status reporting.

## Controls, data, and evidence

Define pools and mappings in versioned configuration with named owners. Separate read and write lanes when write saturation has greater consequences. Use independent connection pools for critical control-plane operations so a saturated data plane cannot block cancellation or health checks. Cap queue length as well as concurrency; an unbounded queue merely moves exhaustion.

Record admission class, authenticated principal, pools requested, permit wait and hold durations, queue outcome, lease token, release reason, and policy revision. Metrics should aggregate utilization, saturation, queue delay, rejection, starvation age, and leaked permits by bounded labels. Evidence includes capacity models, load-test results, tenant-isolation tests, pool-change approvals, and recovery drills. Review whether reserved capacity is actually available during incidents rather than only represented in configuration.

## Validation tests

Flood one tenant to its concurrency and queue ceilings; another tenant's reserved capacity must remain usable. Saturate a noncritical tool pool and verify cancellation, authorization, and health operations still run. Spawn children from a saturated run and confirm they remain in the same accounting domain. Kill a worker while it holds permits and verify leases expire and stale holders cannot commit.

Create tasks needing two pools in opposite order and confirm canonical acquisition prevents deadlock. Test queue expiration before dispatch and verify expired work never executes later. Run mixed short and long jobs to measure starvation. Attempt to choose an emergency class through prompt content or untrusted metadata. Reduce pool size while permits are held and verify no new admissions occur until usage falls below the new ceiling. Confirm overload errors are stable and do not trigger uncontrolled retries.

## Failure handling

If the scheduler cannot determine a workload class, place the run in a restrictive default pool or reject it. If permit storage becomes unavailable, stop admitting side-effecting work and preserve a small local allowance only when explicitly designed for partition operation. Do not create unlimited local capacity as a fallback.

When a permit leak is suspected, reconcile active leases against worker ownership before reclaiming. Fencing tokens must protect downstream commits from a worker that resumes after reclamation. If an isolation mapping proves incorrect, freeze configuration changes, route affected classes to a conservative pool, and preserve admission records for analysis. Capacity borrowed from another class should be revocable, bounded, and recorded.

## Limitations

Bulkheads reduce blast radius but lower peak utilization and require defensible classification. A shared dependency outside the controlled pools can still couple tenants. Reserved capacity may sit idle, while borrowing rules can undermine guarantees. Concurrency is an imperfect proxy for CPU, memory, token, or cost consumption. Multi-resource scheduling can still produce priority inversion. Isolation also does not establish data separation or authorization; those require independent controls.

## Canonical sources

- **OWASP, Denial of Service Cheat Sheet:** https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html
- **NIST, SP 800-53 Revision 5:** https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- **IETF, RateLimit Fields for HTTP (RFC 9333):** https://www.rfc-editor.org/rfc/rfc9333.html
