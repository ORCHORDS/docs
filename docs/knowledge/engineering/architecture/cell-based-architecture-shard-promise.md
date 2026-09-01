# Cell Based Architecture Shard Promise

## Scope

This article addresses the cell-based architecture pattern as a generalisation of database sharding taken up through the entire stack. It explains how the cell—the self-contained unit of compute, storage, and routing—promises isolation of failure, isolation of blast radius, isolation of deployment, and isolation of team autonomy, and where that promise breaks down in practice. It covers the relationship between cells and shards, between cells and multi-region deployments, between cells and multi-tenancy, and between cells and bulkheads. The discussion is project-neutral and applies to any system large enough that a single failure domain is unacceptable. It does not prescribe a specific cell router implementation, although the principles apply equally to a Cloudflare Worker acting as a cell router and to a managed load balancer with consistent hashing.

## Workflow or implementation guidance

The cell pattern begins with a promise that is easy to state and hard to honour: each cell must be able to serve its traffic independently, with no synchronous dependency on any other cell. To honour that promise, each cell contains its own application servers, its own database (or its own partition of a logically-shared database), its own caches, its own queues, and its own observability stack. The cell is identical in code and configuration to every other cell; the only thing that differs is the data it owns and the traffic it serves.

The first step in adoption is to choose the routing key. The routing key is the field that determines which cell a request lands in, and it is load-bearing for the lifetime of the system. A bad routing key—unstable, unavailable on every request, or unevenly distributed—forces costly rebalancing later. The second step is to design the cell router. The router must be stateless, must be highly available, must direct each request to the correct cell in constant or near-constant time, and must degrade gracefully if a cell is unhealthy. The third step is to remove every synchronous cross-cell call. Cross-cell reads can be served from a replicated cache; cross-cell writes must go through an asynchronous path (an event bus, a queue, an outbox) or must not exist at all.

The fourth step is to standardise cell provisioning. Each cell is provisioned from code, identically, with no manual steps. A new cell comes up empty, populates its reference data from a controlled source, warms its caches, and is added to the router. This is the operational discipline that makes the cell pattern sustainable; without it, cells drift and the promise of independence is broken. The fifth step is to define the migration path. Tenants will eventually need to move between cells for rebalancing, isolation of a noisy neighbour, or compliance. The migration must be a documented, rehearsed operation: dual-write to both cells, backfill from the source of truth, cut over reads, and decommission the old cell.

The promise extends to deployment. A cell-by-cell rollout turns a single global deploy into N smaller deploys, each with a bounded blast radius. If Cell 3 of 10 fails, only 10 percent of traffic is affected, and the failure is contained. The promise also extends to compliance: a cell may be pinned to a region for data residency, and a noisy neighbour can be moved into its own cell without affecting the rest of the fleet.

## Controls

The cell architecture has three load-bearing controls: the routing table, the per-cell health signal, and the cell provisioning pipeline. The routing table must be authoritative, versioned, and replayable; a wrong routing entry can either drop traffic or send it to a cell that does not have the data. The per-cell health signal must include liveness, readiness, and capacity. Liveness checks the cell process; readiness checks the cell's dependencies (database, caches); capacity checks whether the cell can absorb more traffic. The cell provisioning pipeline must produce a cell that is byte-identical in code and configuration to every other cell.

Audit controls include tenant placement records (which tenant is in which cell), per-cell compliance posture (which region the cell runs in, which encryption keys it uses), and per-cell SLO dashboards. Without these, "which cell is tenant X in?" becomes an unanswerable question during an incident.

## Validation evidence

Validation of the cell architecture is structural and operational. Structural validation proves that there are no synchronous cross-cell calls in the hot path; this is typically done by inspecting traces and by introducing artificial latency in one cell and verifying that other cells are unaffected. Operational validation proves that the routing key is stable and evenly distributed: a bad routing key shows up as skewed cell utilisation under uniform traffic, and the validation must catch that before production. Provisioning validation proves that the cell pipeline produces a working cell in a documented time; this is typically a chaos test in which a cell is destroyed and rebuilt, and the rebuilt cell must serve its share of traffic within the recovery SLO.

Migration validation proves that tenants can be moved between cells without downtime. A rehearsed migration exercises dual-write, backfill, read cutover, and decommission, and asserts that no tenant sees a read-your-writes violation and no request is lost.

## Failure modes and correction

The most common failure is a hidden synchronous cross-cell call. The system looks like a cell architecture on the diagram, but a single synchronous read from Cell B into Cell A's database exists in one service. Under normal load it is invisible; under Cell A's failure it is the cause of the cascading outage. The cure is to make cross-cell calls visible—lint the codebase, instrument the trace, fail the build if a synchronous call crosses a cell boundary. The second failure is the routing key being wrong. The cure is to invest in the routing key choice up front and to design the routing table so that it can be reshuffled without a global outage.

A third failure is uneven cell sizing. The router uses a hash that produces an unbalanced distribution, and one cell holds 70 percent of the traffic. The cure is to use consistent hashing with virtual nodes, or to use an explicit placement table that can be adjusted. A fourth failure is operational drift. Cells were identical on day one but accumulated differences through ad hoc fixes. The cure is to rebuild from the pipeline and to forbid in-place changes. A fifth failure is the migration tooling never being exercised. The cure is to run a tenant migration in staging at least once per quarter.

## Limitations

The cell pattern is expensive. Each cell pays for its own database, caches, observability, and warming infrastructure, and the marginal cost of the Nth cell must be justified by the isolation benefit. The pattern also forces the system to give up cross-cutting queries: a single SQL join across all tenants is no longer possible, and any analytics that requires a global view must be implemented as a replicated read model fed by the cells' event streams. The pattern assumes that the system can tolerate "no synchronous cross-cell call" as a design constraint; if the business requirement is real-time global consistency, cells are the wrong choice. Finally, the cell pattern does not protect against failures that originate at the routing tier itself; the router is a new critical path and must be designed and operated accordingly.

## Canonical sources

- AWS Architecture Blog — posts on cell-based architecture for tenant isolation, including AWS's own internal use of the pattern (see AWS re:Invent and Builder's Library pieces): https://aws.amazon.com/blogs/architecture/
- AWS Well-Architected Reliability pillar — multi-cell and multi-region guidance: https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/
- AWS Builder's Library — articles by AWS principal engineers on cell-based design, including Adrian Cockcroft and Colm MacCárthaigh's writing
- Microsoft Azure Architecture Center — *Isolation patterns* and discussion of cells as a deployment topology
