# database-read-replicas

**Issue:** Using read replicas to offload read traffic and scale query throughput
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Primary database CPU at 80%+ with analytical queries and application reads competing. Single replica lag increasing during peak write periods.

## Pattern / Solution
Read replica patterns:
```python
# Application-level read/write splitting
import psycopg2
from contextlib import contextmanager

PRIMARY_DSN = "host=primary-db.rds.amazonaws.com dbname=app user=app"
REPLICA_DSN = "host=replica-db.rds.amazonaws.com dbname=app user=app"

@contextmanager
def get_write_conn():
    conn = psycopg2.connect(PRIMARY_DSN)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

@contextmanager
def get_read_conn():
    conn = psycopg2.connect(REPLICA_DSN)
    conn.set_session(readonly=True)
    try:
        yield conn
    finally:
        conn.close()
```

RDS read replica promotion (failover):
```bash
aws rds promote-read-replica \
  --db-instance-identifier my-replica \
  --backup-retention-period 7
# Takes ~5 minutes; replica becomes standalone primary
```

Aurora read endpoint (auto-distributes across replicas):
```hcl
resource "aws_rds_cluster_instance" "replicas" {
  count              = 2
  cluster_identifier = aws_rds_cluster.main.id
  instance_class     = "db.r8g.xlarge"
  engine             = aws_rds_cluster.main.engine
}
# Use cluster reader endpoint: cluster.cluster-ro-xxxx.region.rds.amazonaws.com
```

Replica lag monitoring:
```sql
-- On replica, check replication lag
SELECT EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp())) AS lag_seconds;
```

## Gotchas
- Reads to replica after write may return stale data — implement read-your-writes by routing post-write reads to primary for N seconds
- Aurora replicas share the same storage — no lag for storage replication, only for buffer cache sync
- Replica counts toward connection limit of the instance class — size replicas independently
- Promoting a replica to primary does not update DNS automatically (RDS does, Aurora does not for standalone replicas)

## Related
- `aws-rds-multi-az.md`
- `postgresql-replication-lag.md`
- `connection-pooling-strategies.md`
