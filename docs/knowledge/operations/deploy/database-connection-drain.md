# database-connection-drain

**Issue:** Gracefully draining database connections before a deployment or failover
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Abrupt pod termination mid-transaction causes data corruption, transaction rollbacks, and client errors. Connection draining ensures in-flight transactions complete before the connection pool is closed.

## Pattern / Solution
Application-level graceful shutdown (Node.js + pg):
```javascript
const pool = new Pool({ connectionString: process.env.DATABASE_URL });

process.on('SIGTERM', async () => {
  console.log('SIGTERM received — draining connections');

  // Stop accepting new HTTP requests
  server.close(async () => {
    // Wait for active queries to complete
    await pool.end();
    console.log('Database pool closed');
    process.exit(0);
  });

  // Force exit after timeout
  setTimeout(() => {
    console.error('Drain timeout — forcing exit');
    process.exit(1);
  }, 30_000);
});
```

Kubernetes terminationGracePeriodSeconds:
```yaml
spec:
  terminationGracePeriodSeconds: 60   # must be > drain timeout
  containers:
  - name: api
    lifecycle:
      preStop:
        exec:
          command: ["/bin/sh", "-c", "sleep 5"]  # wait for load balancer deregistration
```

PgBouncer connection pooler drain (before DB maintenance):
```bash
# Pause new connections
psql -h pgbouncer -p 5432 pgbouncer -c "PAUSE myapp_db;"

# Wait for active queries
psql -h pgbouncer -p 5432 pgbouncer -c "SHOW POOLS;" | grep myapp_db

# After maintenance, resume
psql -h pgbouncer -p 5432 pgbouncer -c "RESUME myapp_db;"
```

RDS blue/green deployment connection drain:
```bash
# AWS RDS Blue/Green — connection drain is automatic before switchover
aws rds switchover-blue-green-deployment \
  --blue-green-deployment-identifier bgd-abc123 \
  --switchover-timeout 300
```

## Gotchas
- `preStop: sleep 5` is a workaround for the race between Kubernetes removing the pod from endpoints and sending SIGTERM
- `terminationGracePeriodSeconds` is measured from SIGTERM, including the `preStop` hook; set it larger than your drain timeout
- Long-running batch jobs may not complete within the grace period; implement checkpointing for resumable processing
- Connection pool libraries (pgbouncer, pgpool) track connections at the proxy layer; application-level drain must coordinate with the pool
- MySQL/Aurora `SET GLOBAL wait_timeout` forces idle connections closed but does not drain active queries

## Related
- `graceful-shutdown-patterns.md`
- `database-migration-zero-downtime.md`
- `kubernetes-rolling-update.md`
- `zero-downtime-deploys.md`
