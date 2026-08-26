# Database Query Optimization

Database query optimization is crucial for maintaining application performance and scalability. Optimized queries reduce resource consumption, improve response times, and handle increased user loads effectively.

## EXPLAIN ANALYZE

Use `EXPLAIN ANALYZE` to understand query execution plans and identify bottlenecks:

```sql
EXPLAIN ANALYZE SELECT * FROM users WHERE email = 'user@example.com';
```

This shows actual execution costs, rows processed, and timing information. Look for full table scans (bad) versus index scans (good).

## Slow Query Log

Enable slow query logging to identify problematic queries:

```sql
-- MySQL configuration
slow_query_log = 1
long_query_time = 2
log_queries_not_using_indexes = 1
```

Monitor queries exceeding the threshold. These are typically candidates for optimization.

## Index Strategy

Create strategic indexes on frequently queried columns:

```sql
-- Bad: No index
SELECT * FROM orders WHERE customer_id = 123;

-- Good: Proper index
CREATE INDEX idx_orders_customer_id ON orders(customer_id);

-- Composite indexes for multiple conditions
CREATE INDEX idx_orders_customer_date ON orders(customer_id, order_date);
```

Avoid over-indexing as it slows down INSERT/UPDATE operations.

## Join Optimization

Optimize joins by ensuring proper indexing and query structure:

```sql
-- Bad: Nested loop join without index
SELECT u.name, o.total
FROM users u, orders o
WHERE u.id = o.user_id;

-- Good: Proper indexed join
SELECT u.name, o.total
FROM users u
INNER JOIN orders o ON u.id = o.user_id;
```

Use `EXPLAIN` to verify join execution plans and avoid Cartesian products.

## N+1 Detection

Prevent N+1 query problems in ORM frameworks:

```python
# Bad: N+1 queries
for user in users:
    print(user.name)
    for order in user.orders:  # Executes separate query per user
        print(order.total)

# Good: Eager loading
users = User.objects.prefetch_related('orders')
for user in users:
    print(user.name)
    for order in user.orders:  # No additional queries
        print(order.total)
```

## Query Caching

Implement caching to reduce database load:

```sql
-- MySQL query cache (deprecated in 8.0+)
SELECT SQL_CACHE * FROM products WHERE category = 'electronics';

-- Application-level caching example
cache.set('products_electronics', products, timeout=3600);
```

Use Redis or Memcached for efficient caching strategies.

## Common pitfalls

- **Ignoring indexes**: Queries without proper indexes cause full table scans
- **Over-indexing**: Too many indexes slow down write operations
- **SELECT ***: Retrieving unnecessary columns increases I/O
- **Missing WHERE clauses**: Accidentally scanning entire tables
- **Inefficient JOINs**: Not using appropriate join
