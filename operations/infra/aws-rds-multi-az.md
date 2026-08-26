# aws-rds-multi-az

**Issue:** Configuring RDS Multi-AZ for high availability and understanding its limits
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Single-AZ RDS instances go down during maintenance windows or AZ failures. Teams conflate Multi-AZ (HA) with Read Replicas (scale-out) and misconfigure both.

## Pattern / Solution
```hcl
# Terraform
resource "aws_db_instance" "main" {
  identifier        = "prod-postgres"
  engine            = "postgres"
  engine_version    = "16.3"
  instance_class    = "db.r8g.2xlarge"
  allocated_storage = 500
  storage_type      = "gp3"
  iops              = 12000

  multi_az               = true   # synchronous standby in another AZ
  backup_retention_period = 7
  deletion_protection    = true

  # Performance Insights
  performance_insights_enabled = true
  performance_insights_retention_period = 7
}
```

Failover typically takes 60–120 s. The CNAME endpoint flips automatically — no client change needed if using the cluster endpoint.

For RDS Multi-AZ Cluster (2 readable standbys, ~35 s failover):
```hcl
resource "aws_rds_cluster" "main" {
  cluster_identifier = "prod-pg-cluster"
  engine             = "aurora-postgresql"
  engine_version     = "16.2"
  availability_zones = ["us-east-1a", "us-east-1b", "us-east-1c"]
}
```

## Gotchas
- Multi-AZ standby is NOT readable — use Read Replicas for read scaling
- Storage autoscaling can trigger I/O freeze during expansion on gp2; use gp3 with pre-set IOPS
- Maintenance window applies to primary; standby is patched first, then failover occurs
- Cross-region Read Replicas have async replication lag — not suitable for zero-RPO

## Related
- `postgresql-replication-lag.md`
- `database-read-replicas.md`
- `postgresql-backup-restore.md`
