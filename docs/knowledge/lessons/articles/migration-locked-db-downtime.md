# Migration That Locked the Database: A Production Downtime Nightmare

## Symptom

Your database migration process hangs indefinitely, causing production downtime and user complaints. The application becomes unresponsive as all connections wait for locks to be released. You notice that `SHOW PROCESSLIST` reveals multiple queries stuck in "Locked" state, with the migration query holding an exclusive lock on critical tables.

## Gotchas

### The Expand-Contract Pattern Trap
The most common cause occurs when using expand-contract pattern without proper lock management. When you add new columns or indexes to large production tables, MySQL acquires table locks that can last for hours, especially with millions of rows.

### ALTER TABLE Lock Behavior
`ALTER TABLE` operations in MySQL often require:
- Exclusive table locks (metadata and data)
- Full table scans for certain operations
- Lock escalation when dealing with large datasets

### Production Environment Risks
- No staging environment to test lock duration
- Lack of monitoring during migration
- Ignoring existing connection limits
- Underestimating impact of concurrent user activity

## Practical Solutions

### Migration Safety Checklist
1. **Test in staging** - Replicate production data size and load
2. **Monitor lock duration** - Use `SHOW ENGINE INNODB STATUS` before running migrations
3. **Schedule during low traffic** - Plan outside peak usage hours
4. **Implement connection limits** - Reduce concurrent connections during migration
5. **Use pt-online-schema-change** - For large tables, avoid direct ALTER TABLE

### Lock Management Techniques
```sql
-- Check current locks before migration
SHOW ENGINE INNODB STATUS\G

-- Monitor progress during migration
SELECT * FROM INFORMATION_SCHEMA.PROCESSLIST
WHERE COMMAND = 'Query' AND TIME > 60;

-- Use smaller batches for large data operations
UPDATE table_name SET column = value WHERE id BETWEEN 1 AND 1000;
```

### Preventive Measures
- Implement gradual migration strategies
- Use read replicas for heavy operations
- Set up automated alerts for long-running queries
- Document expected lock times for each migration type

## Recovery Steps

If you encounter a locked database:
1. Kill the problematic process immediately
2. Review and optimize your migration strategy
3. Implement proper monitoring in production
4. Create rollback procedures for future migrations

The key is understanding that database migrations aren't just about changing schema - they're about managing locks, connections, and user experience
