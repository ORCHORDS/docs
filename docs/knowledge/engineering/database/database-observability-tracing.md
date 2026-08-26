# Database Observability and Query Tracing

## Overview

Database observability is crucial for maintaining high-performance applications and identifying bottlenecks in production systems. Modern database monitoring requires comprehensive visibility into query execution, performance metrics, and resource utilization across your entire database infrastructure.

## Symptom

Common database performance issues include:
- Slow query execution affecting user experience
- Resource contention leading to timeouts
- Unexpected database load spikes during peak hours
- Inefficient query patterns causing excessive I/O
- Missing indexes resulting in full table scans
- Connection pool exhaustion impacting application availability

## Gotchas

Database monitoring often suffers from:
- Incomplete query tracing due to parameterized queries
- Missing correlation between application and database metrics
- Overhead from extensive logging affecting performance
- Complex query parsing making analysis difficult
- Limited visibility into distributed database transactions
- Inconsistent tagging strategies across different systems
- Tool integration challenges between monitoring platforms

## Core Monitoring Solutions

### pg_stat_statements Extension

The `pg_stat_statements` extension provides comprehensive query statistics for PostgreSQL databases. Enable it with:

```sql
-- Enable extension
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Configure settings
ALTER SYSTEM SET pg_stat_statements.max = 10000;
ALTER SYSTEM SET pg_stat_statements.save = on;
SELECT pg_reload_conf();
```

Monitor query performance using:
```sql
-- View top queries by execution time
SELECT
    calls,
    total_time,
    mean_time,
    query
FROM pg_stat_statements
ORDER BY total_time DESC
LIMIT 10;
```

### Slow Query Log Configuration

Configure slow query logging to capture performance issues:

```sql
-- PostgreSQL slow query log settings
ALTER SYSTEM SET log_min_duration_statement = 1000; -- Log queries taking >1s
ALTER SYSTEM SET log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h ';
SELECT pg_reload_conf();
```

### OpenTelemetry Database Spans

Implement OpenTelemetry database tracing for distributed monitoring:

```yaml
# OpenTelemetry configuration example
exporters:
  otlp:
    endpoint: "localhost:4317"
    tls:
      insecure: true
processors:
  batch:
    timeout: 5s
service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp]
```

### Query Tags and Metadata

Use query tags to correlate database activity with application context:

```sql
-- Parameterized queries with tags
SELECT * FROM users
WHERE user_id = $1 AND status = $2
/* tag: user_profile_query */;

UPDATE orders
SET status = $1, updated_at = NOW()
WHERE order_id = $2
/* tag: order_update_operation */;
```

### Datadog Database Monitoring

Configure
