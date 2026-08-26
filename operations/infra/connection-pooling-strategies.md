# connection-pooling-strategies

**Issue:** Database connection pooling architecture to handle thousands of app instances without overwhelming the database
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
PostgreSQL "too many connections" errors when deploying many Lambda functions, containers, or serverless instances that each open their own connection pool.

## Pattern / Solution
Layer 1 — Application-level pool (within a process):
```python
# SQLAlchemy pool per process
engine = create_engine(
    DATABASE_URL,
    pool_size=5,           # connections kept open
    max_overflow=10,       # burst connections above pool_size
    pool_timeout=30,       # wait time before error
    pool_pre_ping=True     # verify connection alive before using
)
```

Layer 2 — External proxy pool (PgBouncer):
```ini
# pgbouncer.ini
[databases]
mydb = host=postgres-primary port=5432 dbname=mydb

[pgbouncer]
listen_port = 6432
pool_mode = transaction         # best for serverless; releases conn after each tx
max_client_conn = 10000         # accepts many app connections
default_pool_size = 25          # opens only 25 server connections
min_pool_size = 5
reserve_pool_size = 5
reserve_pool_timeout = 3
server_idle_timeout = 600
```

RDS Proxy (managed PgBouncer for AWS):
```hcl
resource "aws_db_proxy" "main" {
  name                   = "prod-rds-proxy"
  engine_family          = "POSTGRESQL"
  role_arn               = aws_iam_role.rds_proxy.arn
  vpc_subnet_ids         = var.private_subnet_ids

  auth {
    auth_scheme = "SECRETS"
    secret_arn  = aws_secretsmanager_secret.db_creds.arn
    iam_auth    = "REQUIRED"
  }

  connection_borrow_timeout = 120
  max_connections_percent   = 90
}
```

Connection limit calculator:
```
Max DB connections ≈ (RAM in GB × 1024 / 10) - 45
e.g. db.r8g.xlarge (32 GB RAM): ~3236 max connections
Reserve 10% for superuser: 2912 usable
PgBouncer pool_size: 100 (well below limit even with 30 replicas)
```

## Gotchas
- PgBouncer `transaction` mode breaks `SET`, `LISTEN/NOTIFY`, prepared statements — use `session` mode if needed
- RDS Proxy requires Secrets Manager; connection strings must use the proxy endpoint
- Application-level pool + PgBouncer: each PgBouncer server connection can be shared by many clients — don't double-count
- Lambda with RDS Proxy: each Lambda cold start opens a new client connection to proxy (cheap); proxy manages server connections

## Related
- `postgresql-connection-pooling-pgbouncer.md`
- `database-read-replicas.md`
- `aws-rds-multi-az.md`
