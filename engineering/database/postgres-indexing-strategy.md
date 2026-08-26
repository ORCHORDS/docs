# PostgreSQL Indexing Strategy

## Symptom

Slow query performance, especially on large tables with frequent WHERE clauses, JOINs, or ORDER BY operations. Queries that should be fast are taking minutes instead of milliseconds.

## Gotchas

- **Index selection confusion**: Developers often choose the wrong index type for their data patterns
- **Over-indexing**: Creating too many indexes slows down INSERT/UPDATE/DELETE operations
- **Missing index statistics**: Not understanding when indexes are actually used
- **Partial index misuse**: Creating partial indexes without proper WHERE conditions

## Index Types Comparison

### B-tree Indexes
Best for equality and range queries on simple data types:
```sql
-- Basic B-tree index
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_orders_date ON orders(order_date);

-- Multi-column B-tree
CREATE INDEX idx_orders_customer_date ON orders(customer_id, order_date);
```

### GIN Indexes
Ideal for complex data types like arrays, JSON, text search:
```sql
-- Array indexing
CREATE INDEX idx_products_tags ON products USING GIN(tags);

-- JSONB indexing
CREATE INDEX idx_users_profile ON users USING GIN(profile);

-- Text search indexing
CREATE INDEX idx_articles_search ON articles USING GIN(to_tsvector('english', content));
```

### GiST Indexes
Good for geometric data and full-text search:
```sql
-- Geometry indexing
CREATE INDEX idx_locations_geom ON locations USING GiST(geom);

-- Full-text search
CREATE INDEX idx_articles_fts ON articles USING GiST(textsearchable);
```

## Partial Indexes

Create indexes that cover only specific data subsets:
```sql
-- Only index active users
CREATE INDEX idx_active_users_email ON users(email) WHERE is_active = true;

-- Index recent orders only
CREATE INDEX idx_recent_orders_date ON orders(order_date)
WHERE order_date > '2023-01-01';

-- Index specific status combinations
CREATE INDEX idx_orders_processing ON orders(status, customer_id)
WHERE status IN ('processing', 'shipped');
```

## Expression Indexes

Index computed values or function results:
```sql
-- Case-insensitive email lookup
CREATE INDEX idx_users_email_lower ON users(LOWER(email));

-- Extract year from date
CREATE INDEX idx_orders_year ON orders(EXTRACT(YEAR FROM order_date));

-- Concatenated fields
CREATE INDEX idx_user_fullname ON users(CONCAT(first_name, '
