# check-constraints

**Issue:** Enforcing domain rules at the database level with CHECK constraints
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Application-level validation can be bypassed by direct DB access or bugs; CHECK constraints guarantee invariants at the storage layer.

## Pattern / Solution
```sql
CREATE TABLE products (
  id         BIGSERIAL PRIMARY KEY,
  price_cents INT NOT NULL CHECK (price_cents >= 0),
  status     TEXT NOT NULL CHECK (status IN (''active'', ''inactive'', ''draft'')),
  weight_kg  NUMERIC CHECK (weight_kg > 0),
  start_date DATE,
  end_date   DATE,
  CONSTRAINT valid_date_range CHECK (end_date IS NULL OR end_date >= start_date)
);

-- Named constraint for better error messages
ALTER TABLE orders
  ADD CONSTRAINT chk_qty_positive CHECK (quantity > 0);
```

## Gotchas
- CHECK constraints with `NULL` columns: `NULL` comparisons return UNKNOWN, so NULLs pass most checks — add NOT NULL if required
- Cannot reference other tables inside CHECK (use triggers for cross-table rules)
- Renaming enums requires dropping and recreating the constraint

## Related
- `unique-constraints.md`
- `foreign-key-constraints.md`
