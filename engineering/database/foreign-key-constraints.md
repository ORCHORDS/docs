# foreign-key-constraints

**Issue:** Using foreign key constraints to enforce referential integrity
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Without FK constraints, orphaned rows accumulate silently and data integrity must be enforced entirely in application code.

## Pattern / Solution
```sql
CREATE TABLE orders (
  id          BIGSERIAL PRIMARY KEY,
  customer_id BIGINT NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
  product_id  BIGINT         REFERENCES products(id)  ON DELETE SET NULL
);

-- Deferred FK check (useful for circular dependencies or bulk loads)
ALTER TABLE order_items
  ADD CONSTRAINT fk_order FOREIGN KEY (order_id) REFERENCES orders(id)
  DEFERRABLE INITIALLY DEFERRED;
```

## Gotchas
- `ON DELETE CASCADE` is convenient but can cause unexpected mass-deletes
- FKs on unindexed columns cause full table scans during parent deletes
- Always index the FK column on the child table
- Deferrable FKs add overhead; only use when necessary

## Related
- `check-constraints.md`
- `soft-delete-schema-design.md`
