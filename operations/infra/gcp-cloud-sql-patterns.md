# gcp-cloud-sql-patterns

**Issue:** Cloud SQL for PostgreSQL production patterns including HA, connection management, and backups
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cloud SQL instances have connection limits exceeded, no HA failover configured, or backups not verified.

## Pattern / Solution
```hcl
resource "google_sql_database_instance" "main" {
  name             = "prod-postgres"
  database_version = "POSTGRES_16"
  region           = "us-central1"
  deletion_protection = true

  settings {
    tier              = "db-custom-4-16384"   # 4 vCPU, 16 GB RAM
    availability_type = "REGIONAL"            # HA with standby in another zone

    backup_configuration {
      enabled                        = true
      start_time                     = "03:00"
      point_in_time_recovery_enabled = true
      backup_retention_settings {
        retained_backups = 30
      }
    }

    maintenance_window {
      day          = 7   # Sunday
      hour         = 4
      update_track = "stable"
    }

    database_flags {
      name  = "max_connections"
      value = "500"
    }
    database_flags {
      name  = "cloudsql.enable_pgaudit"
      value = "on"
    }
  }
}
```

Use Cloud SQL Auth Proxy for secure connections (no VPN needed):
```bash
# Run as sidecar in Cloud Run or GKE
cloud-sql-proxy PROJECT:REGION:INSTANCE \
  --port=5432 \
  --credentials-file=/secrets/sa-key.json
```

Or use the Kubernetes operator:
```yaml
# PodSpec annotation
annotations:
  cloudsql.googleapis.com/instances: "PROJECT:REGION:INSTANCE=tcp:5432"
```

## Gotchas
- `REGIONAL` availability costs 2× compute — worth it for production; use `ZONAL` for dev
- Max connections limit per tier — use PgBouncer sidecar or Cloud SQL's built-in connection pooling (preview)
- Point-in-time recovery requires binary logging enabled — it's on by default with backups
- IOPS scale with disk size — minimum 10 GB recommended even if data is small

## Related
- `postgresql-connection-pooling-pgbouncer.md`
- `gcp-iam-workload-identity.md`
- `database-read-replicas.md`
