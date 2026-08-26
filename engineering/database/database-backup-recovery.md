# Database Backup and Recovery Strategy

## Overview

A robust database backup and recovery strategy is essential for business continuity and data protection. This article covers key concepts including pg_dump vs WAL archiving, point-in-time recovery (PITR), backup testing procedures, and disaster recovery planning.

## pg_dump vs WAL Archiving

**pg_dump** provides logical backups of database schemas and data, creating SQL scripts or custom binary formats. It's ideal for database migrations and application-level backups.

```bash
# Basic pg_dump example
pg_dump -h hostname -U username database_name > backup.sql

# Custom format backup (faster restore)
pg_dump -F c -h hostname -U username database_name > backup.custom
```

**WAL archiving** captures write-ahead log files for point-in-time recovery. It's crucial for continuous data protection and minimal recovery points.

```bash
# Enable WAL archiving in postgresql.conf
wal_level = replica
archive_mode = on
archive_command = 'cp %p /var/lib/postgresql/wal_archive/%f'
```

## Point-in-Time Recovery (PITR)

PITR allows restoration to any specific moment within the backup window using archived WAL files. This enables recovery from accidental deletions or corruption.

```bash
# Restore to specific timestamp
pg_restore -d database_name backup.custom
# Then apply WAL files to reach desired point in time

# Example recovery.conf configuration
restore_command = 'cp /var/lib/postgresql/wal_archive/%f %p'
recovery_target_time = '2024-01-15 14:30:00'
```

## Backup Testing and Validation

Regular backup testing ensures recovery procedures work correctly. Test restores should be performed monthly with production-like data sets.

```bash
# Test restore procedure
pg_restore -d test_database backup.custom
psql -d test_database -c "SELECT COUNT(*) FROM table_name;"
```

## RPO/RTO Definitions

**Recovery Point Objective (RPO)** defines maximum acceptable data loss measured in time. For critical systems, RPO should be minutes or hours.

**Recovery Time Objective (RTO)** specifies maximum acceptable downtime for system restoration. Critical applications may require RTO of minutes.

```bash
# Example RPO/RTO configuration
# RPO: 15 minutes - WAL archiving every 5 minutes
# RTO: 30
