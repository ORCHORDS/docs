# normalization-denormalization-tradeoffs

**Issue:** When to normalize vs. denormalize for performance vs. integrity
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Normalized schemas eliminate redundancy but require joins; denormalized schemas are fast to read but hard to keep consistent.

## Pattern / Solution
```sql
-- Normalized: orders reference customers by FK
CREATE TABLE orders (
  id          BIGSERIAL PRIMARY KEY,
  customer_id BIGINT NOT NULL REFERENCES customers(id),
  total_cents INT NOT NULL
);

-- Denormalized: store customer_email on orders for read speed
ALTER TABLE orders ADD COLUMN customer_email TEXT;

-- Hybrid: use materialized views for reporting
CREATE MATERIALIZED VIEW order_summary AS
SELECT o.id, c.email, o.total_cents
FROM orders o JOIN customers c ON c.id = o.customer_id;
```

## Gotchas
- Denormalized copies must be kept in sync — use triggers or application logic
- Materialized views need explicit REFRESH; data can be stale
- 3NF is a good default; BCNF for strict integrity, 1NF minimum always

## Related
- `schema-design-principles.md`
- `covering-indexes.md`
