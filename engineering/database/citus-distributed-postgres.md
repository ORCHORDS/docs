# Citus: Distributed PostgreSQL

## Overview

Citus is an open-source extension that transforms PostgreSQL into a distributed database system, enabling horizontal scaling across multiple nodes. Built on top of PostgreSQL's native architecture, Citus provides seamless integration while offering powerful distributed querying capabilities through sharding, parallel execution, and automatic load balancing.

## Sharding by tenant_id

Citus excels at multi-tenant architectures where data is partitioned by `tenant_id`. This approach ensures that all data for a specific tenant resides on the same shard, enabling efficient queries and maintaining data locality. The distributed table creation syntax uses `DISTRIBUTED BY` clause:

```sql
CREATE TABLE user_events (
    id bigserial PRIMARY KEY,
    tenant_id bigint NOT NULL,
    event_type text NOT NULL,
    created_at timestamp DEFAULT now()
) DISTRIBUTED BY (tenant_id);
```

This sharding strategy is particularly effective for SaaS applications where each tenant's data needs to be isolated and queried efficiently.

## Distributed Tables vs Reference Tables

Distributed tables are partitioned across multiple nodes based on a distribution column, while reference tables contain complete copies of data on every node. Distributed tables are ideal for large datasets with natural sharding columns, whereas reference tables work best for small lookup tables that need to be joined frequently:

```sql
-- Distributed table (sharded)
CREATE TABLE orders (
    order_id bigserial PRIMARY KEY,
    customer_id bigint NOT NULL,
    amount numeric(10,2),
    created_at timestamp DEFAULT now()
) DISTRIBUTED BY (customer_id);

-- Reference table (replicated)
CREATE TABLE countries (
    country_code char(2) PRIMARY KEY,
    country_name text NOT NULL
) DISTRIBUTED REPLICATED;
```

## Colocated Joins

Citus automatically optimizes joins between colocated tables - tables that share the same distribution column. When tables are colocated, Citus can perform local joins without network overhead:

```sql
-- These tables are colocated on customer_id
SELECT o.order_id, c.country_name
FROM orders o
JOIN countries c ON o.customer_id = c.country_code
WHERE o.created_at > $1;
```

## Rebalancing

Citus automatically rebalances data across nodes when new workers are added or removed. The system monitors node load and redistributes shards to maintain optimal performance. Manual rebalancing can be triggered using:

```sql
SELECT rebalance_table_shards('orders');
SELECT rebalance_database_shards();
```

## When to Use Citus vs Vanilla PostgreSQL

**Use Citus when:**
- Data volume exceeds single-node PostgreSQL capacity (100GB+)
- Need horizontal scaling beyond single server limitations
- Require multi-tenant architecture with tenant isolation
- Experience query performance bottlenecks on large datasets
- Need automatic sharding and load balancing

**Stick with vanilla PostgreSQL when:**
- Data size remains under 100GB
- Simple
