# Redis Cluster Failover and Recovery Playbook

## Purpose

Drive predictable Redis Sentinel / Redis Cluster failover, recovery from a master outage, and master rejoin. Covers data loss risk mitigation, client reconnect tuning, and post-failover validation.

## Audience

Database operators, SRE on-call, application owners.

## Pre-conditions

1. The reference card is current: `REDIS_VERSION_GOVERNANCE.md`.
2. Redis Sentinel is configured for HA, or Redis Cluster for sharded HA.
3. Persistence is configured (RDB or RDB + AOF).
4. Client retry / reconnect logic is documented per `OAUTH_INTEGRATION_PLAYBOOK.md` (similar pattern).
5. Monitoring is wired.

## Procedure

### 1. Pre-failover validation

1. Confirm Sentinel / Cluster quorum is healthy.
2. Confirm replica lag is acceptable (≤ 1 second).
3. Confirm persistence (RDB / AOF) is current.
4. Confirm client connection strings are configured with sentinel support (`redis-sentinel://...`).
5. Confirm application is configured to retry with backoff.

### 2. Detect

1. Sentinel: master marked `s_down` / `o_down`.
2. Cluster: master slot moved to a replica.
3. Client errors: `READONLY`, `MASTERDOWN`, `CONNECTION REFUSED`.
4. Trigger the playbook when:
   - Sentinel reports `+switch-master`.
   - Cluster reports slot move.
   - Client error rate > 5% for 5 minutes.

### 3. Failover — Sentinel

1. Sentinel auto-failover kicks in (configured via `sentinel monitor`).
2. Sentinel elects a new master from the available replicas.
3. Sentinel sends `SLAVEOF NO ONE` to the elected replica.
4. Sentinel updates `+switch-master` to the remaining Sentinels and to the clients (via pub/sub).
5. Clients reconnect to the new master.

### 4. Failover — Cluster

1. Cluster detects master failure (cluster-node-timeout default 15s).
2. Cluster promotes a replica to master for the failed slots.
3. Cluster updates slot assignments.
4. Clients receive `MOVED <slot> <new-node>` redirection.
5. Clients connect to the new master.

### 5. Client reconnect

1. Client retries with exponential backoff.
2. Client resolves the new master via Sentinel / Cluster.
3. Client connects to the new master.
4. Client validates the new master with `PING` and `INFO replication`.

### 6. Validate

- Reconnect time ≤ 30 seconds.
- In-flight operations: lost = 0 for ephemeral; lost = N for transactions in flight.
- Data loss: ≤ 1 second (or 0 with synchronous replication).
- Throughput: ≥ baseline post-failover.
- p99 latency: ≤ baseline + 20%.

### 7. Rollback

Rollback of a Redis failover is not possible in the strict sense — once a master has been replaced, the new master holds the role. To revert:

1. Stop writes to the new master.
2. Trigger a planned failover back to the old node (after it's recovered).
3. Validate.

## Mandatory pre-flight (before deploying a new Redis cluster)

1. Sentinel / Cluster is configured.
2. Persistence is configured.
3. Client connection strings support auto-discovery.
4. Backup is current.
5. Monitoring is wired.

## Observability

- `redis_sentinel_known_servers` (gauge).
- `redis_sentinel_master_elected` (counter).
- `redis_replication_lag_seconds` (gauge, per replica).
- `redis_pubsub_channels` (gauge).
- Client connection state per app (gauge).

## References

- `REDIS_VERSION_GOVERNANCE.md`
- `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`
- Redis Sentinel: `https://redis.io/docs/management/sentinel/`
- Redis Cluster: `https://redis.io/docs/management/scaling/`
- Valkey Sentinel: `https://valkey.io/topics/sentinel/`
