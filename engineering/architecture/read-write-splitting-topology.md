# read-write-splitting-topology

**Issue:** Read-heavy services eventually exhaust a single database node, and the standard scaling move is to add read replicas and split traffic: writes to the primary, reads to replicas. The topology decision — where the split happens (client library, proxy, database-native routing, or per-service configuration) and how reads are routed (round-robin, lag-aware, session-aware) — determines whether the feature delivers its promised scalability or introduces a stream of subtle consistency bugs. The canonical failure is the stale read: a user saves a profile, the next page load hits a replica that has not applied the write yet, and the user sees their old data — the read-your-writes problem that DZone, Shopify Engineering, and Arpit Bhayani's consistency writeups all center on. Modern routing solutions answer it with LSN/GTID tracking and causal tokens rather than hoping replication is fast enough. Getting the topology right also decides how painful failover is, because the component that routes reads is the component that must find out, correctly and quickly, that the primary changed.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Topology Options

1. **Client library splitting.** The application uses two connection pools (writer endpoint, reader endpoint) and each query site chooses explicitly, or an ORM flag picks one. Maximum control and zero extra infrastructure; the cost is that every service and every codebase must implement the policy correctly, and configuration drift is guaranteed in polyglot fleets.
2. **Proxy-layer splitting.** A dedicated proxy (ProxySQL, MySQL Router, HAProxy-plus-logic, or cloud proxies) inspects statements and routes writes to the primary and reads to replicas. Centralized policy, language-agnostic, and one place to implement lag-aware routing — at the price of operating another stateful hop with its own failure modes and connection-pooling semantics.
3. **Database-native / managed routing.** Some platforms expose reader endpoints natively (RDS/Aurora reader endpoints, Cloud Spanner, PlanetScale) or do splitting inside the engine (group replication routers). This minimizes ops burden but constrains routing policy to what the platform supports.
4. **Per-service assignment.** Instead of splitting every query, designate some services or endpoints as read-only and point them at replicas, while read-write services stay on the primary. Blunt but predictable: consistency bugs surface as endpoint design decisions rather than per-query accidents.

## Consistency Hazards

1. **Stale reads after write.** The user's own write has not reached the replica when their next read lands on it. Any UI flow of write-then-read (edit profile, then view profile) will exhibit this under load, and users interpret it as data loss.
2. **Cross-entity read anomalies.** Reading entity A from an up-to-date replica and entity B from a lagging one produces incoherent joins (an order with a customer that "does not exist yet"). Round-robin read routing across replicas of differing lag makes this intermittent and hard to reproduce.
3. **Lag spikes under write bursts.** Replication lag is not a constant; it explodes during batch updates, schema migrations, or long transactions. Systems tuned for 200ms lag quietly break at 30s lag, which is exactly when traffic reroutes to replicas because the primary is busy.
4. **Transactions spanning the split.** A read inside a write transaction must hit the primary (or a replica pinned to the transaction snapshot); naive splitting that routes "SELECT" statements by keyword breaks transactional semantics and repeatable-read expectations.

## Routing Techniques

1. **Session pinning after write.** For a window (or until session end) after a user writes, route that user's reads to the primary. Simple and effective for read-your-writes; the costs are reduced replica offload for active writers and choosing the window duration.
2. **LSN / GTID waits.** The robust modern answer: after a write, remember the write's log position (PostgreSQL WAL LSN via pg_current_wal_lsn, MySQL GTID). Before reading from a replica, check whether the replica has applied that position (pg_last_wal_replay_lsn comparison, WAIT_FOR_EXECUTED_GTID_SET) and either wait briefly or fall back to the primary. DZone's PostgreSQL writeup treats this as the reference implementation of read-your-writes in split topologies.
3. **Causal consistency tokens.** The client carries a token from the write response and the proxy only serves the read from replicas that have caught up to that token. This generalizes LSN tracking across proxies and multi-tier architectures, and underlies the causal-session guarantees in systems like MongoDB sessions and Cosmos DB consistency levels.
4. **Lag-aware routing.** Monitor per-replica replication lag and only include replicas in the read pool below a threshold. This protects against anomalies but does not by itself give read-your-writes; pair it with pinning or tokens.
5. **Explicit consistency tiers in the API.** Expose read consistency as an explicit choice per endpoint (fresh reads go primary, tolerant reads go replica). Making the tradeoff visible in code review beats hiding it in a proxy rule nobody remembers.

## Failover and Promotion Concerns

1. **The router is on the failover critical path.** When the primary dies, whatever routes reads and writes must learn the new primary quickly, and must stop sending reads to a replica that is being promoted (it may be briefly writable or inconsistent). Proxies with leader-aware health checks (or patroni-style DNS endpoints) handle this; static configs do not.
2. **Split-brain writes during promotion.** If two layers disagree about who is primary, writes land on both old and new primary, and the divergence requires manual repair. Use fencing (see leader-election-patterns in this KB): only the fenced, current primary should accept writes.
3. **Replica warm-up after promotion.** A freshly promoted primary has no replicas caught up to it; the read pool collapses to one node exactly at the incident. Plan for reduced replica capacity during failover drills.
4. **Connection storms.** Failover invalidates every pooled connection simultaneously; without jittered reconnect and pool caps, the surviving primary gets a thundering herd. Test failover under load, not on an idle system.

## Adoption Decision Guide

1. **Split only when reads are the bottleneck.** Verify with data: if write volume or connection count is the problem, replicas do not help and you need sharding or a different datastore.
2. **Start with endpoint-level splitting, not per-query.** Explicit read-only services/endpoints against reader endpoints deliver most of the offload with none of the proxy semantics risk. Adopt proxy or library splitting when per-query granularity measurably matters.
3. **Implement read-your-writes before you need it.** Retrofitting LSN tracking or session pinning after users report "lost" edits is far more expensive than shipping it with the first split endpoint.
4. **Monitor lag per replica and alert on SLO.** Lag is the honest health metric of the whole topology; a lag dashboard plus alerts on threshold breaches converts silent staleness bugs into visible capacity events.
