# Materialized View Refresh Strategies

Materialized views in PostgreSQL provide powerful caching capabilities for complex queries, but proper refresh strategies are essential for optimal performance and data consistency.

## Symptom

When materialized views aren't refreshed properly, applications may experience stale data reads, performance degradation, or locking issues that impact concurrent operations. Common symptoms include:
- Queries returning outdated data
- Long-running refresh operations blocking concurrent access
- Unexpected lock contention during refresh windows
- Inconsistent data between base tables and materialized views

## Gotchas

Several critical considerations must be addressed when implementing materialized view refresh strategies:

**Unique Index Requirement**: Concurrent refresh requires a unique index on the materialized view. Without it, PostgreSQL cannot guarantee consistency during the refresh operation.

**Locking Behavior**: Full refreshes acquire exclusive locks that block concurrent reads and writes, while concurrent refreshes use row-level locking but require specific indexing.

**Stale Read Risks**: Applications may read partially updated data during refresh operations if not properly configured.

## Refresh Methods

### Concurrent Refresh
```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY schema_name.view_name;
```

Concurrent refresh allows simultaneous read and write operations, making it ideal for high-availability applications. However, it requires a unique index on the materialized view:

```sql
CREATE UNIQUE INDEX idx_mv_unique ON schema_name.view_name (column1, column2);
```

### Scheduled Refresh
```sql
-- Create a scheduled job using pg_cron or similar tool
SELECT cron.schedule('refresh_daily_mv', '0 2 * * *',
    $$REFRESH MATERIALIZED VIEW CONCURRENTLY schema_name.view_name$$);
```

Scheduled refreshes work best for batch processing scenarios where data freshness requirements are less stringent.

### Incremental vs Full Refresh

**Full Refresh**: Rebuilds the entire materialized view, ensuring complete consistency but requiring more resources:
```sql
REFRESH MATERIALIZED VIEW schema_name.view_name;
```

**Incremental Refresh**: Updates only changed data, reducing resource consumption but requiring careful implementation:
```sql
-- Example of incremental approach using a timestamp column
UPDATE schema_name.view_name
SET last_updated = NOW()
WHERE id IN (SELECT id FROM base_table WHERE updated_at > :last_refresh);
```

## Best Practices for 2026

For optimal materialized view refresh strategies in 2026, consider these recommendations:

1. **Implement Concurrent Refresh**: Use `REFRESH MATERIALIZED VIEW CONCURRENTLY` for applications requiring continuous availability
2. **Index Requirements**: Always create unique indexes on materialized views before enabling concurrent refresh
3. **Monitor Locking**: Track lock waits and adjust refresh timing to minimize impact
4. **Stale Read Management**: Implement application-level logic to handle potential stale reads gracefully
5. **Resource Planning**: Schedule heavy refresh operations during low-usage periods

## Practical Implementation

```sql
-- Create materialized
