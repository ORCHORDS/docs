# PostgreSQL Partition Maintenance with pg_partman

## Overview

PostgreSQL partitioning is a powerful feature for managing large datasets efficiently. The `pg_partman` extension simplifies partition maintenance operations, automating routine tasks like partition creation, data movement, and cleanup. This article covers best practices for maintaining PostgreSQL partitions using pg_partman, including automated partition creation, various partitioning strategies, and optimization techniques.

## Symptom

Common issues with partition maintenance include:
- Performance degradation due to missing partition pruning
- Data skew in hash partitions causing uneven distribution
- Manual intervention required for routine partition management
- Inefficient subpartitioning strategies leading to complex query plans
- Missing automated cleanup of old partitions resulting in storage bloat

## Gotchas

Key challenges when working with PostgreSQL partitions:
- Partition pruning requires proper WHERE clause conditions to work effectively
- Hash partitions may experience data skew if the hash key distribution is uneven
- Manual partition management can lead to human error and inconsistent maintenance schedules
- Subpartitioning depth affects query performance and maintenance complexity
- Parameterized queries must use proper syntax to avoid SQL injection vulnerabilities

## Automated Partition Creation

pg_partman automates partition creation through configuration parameters. The extension supports automatic partition creation based on time intervals or value ranges, reducing manual intervention required for routine maintenance.

```sql
-- Create parent table with automated partitioning
SELECT partman.create_parent(
    p_parent_table := 'public.sales_data',
    p_control := 'sale_date',
    p_type := 'time',
    p_interval := '1 month',
    p_constraint_cols := ARRAY['customer_id'],
    p_premake := 2,
    p_start_partition := '2023-01-01'
);

-- Configure automated partition creation
UPDATE partman.part_config
SET premake = 3,
    optimize_trigger = 5,
    retention = '90 days',
    retention_keep_table = true
WHERE parent_table = 'public.sales_data';
```

## Partitioning Types

PostgreSQL supports three main partitioning strategies: range, list, and hash. Each serves different use cases and requires specific configuration approaches.

### Range Partitioning

Range partitioning is ideal for time-series data or numeric ranges where data distribution follows predictable patterns:

```sql
-- Create range partitioned table
SELECT partman.create_parent(
    p_parent_table := 'public.user_activity',
    p_control := 'user_id',
    p_type := 'range',
    p_interval := '10000',
    p_constraint_cols := ARRAY['session_id']
);

-- Add specific range partitions
INSERT INTO partman.part_config (parent_table, control, type, interval, constraint_cols)
VALUES ('public.user_activity', 'user_id', 'range', '50000', ARRAY['session_id']);
```

### List Partitioning

List partitioning works well for categorical data with known discrete values:

```sql
-- Create list partition
