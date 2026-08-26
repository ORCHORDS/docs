# bulk-insert-patterns

**Issue:** Efficiently inserting large volumes of rows
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Row-by-row inserts are slow at scale; bulk techniques can be 10-100x faster.

## Pattern / Solution
```sql
-- Multi-row VALUES
INSERT INTO products (name, price_cents)
VALUES (''Widget A'', 999), (''Widget B'', 1499), (''Widget C'', 299);

-- COPY from stdin (fastest for PostgreSQL)
COPY products (name, price_cents) FROM STDIN WITH (FORMAT csv);

-- COPY from file
COPY products (name, price_cents) FROM ''/tmp/products.csv'' WITH (FORMAT csv, HEADER);

-- Node.js with pg: use COPY via stream
import { from as copyFrom } from ''pg-copy-streams'';
```

```typescript
// Prisma: createMany
await prisma.product.createMany({
  data: products,
  skipDuplicates: true,
});
```

## Gotchas
- COPY bypasses triggers and row-level security — verify this is intentional
- Wrap large bulk inserts in a transaction and commit in batches of 1000-10000 rows
- `COPY` is PostgreSQL-specific; use `LOAD DATA INFILE` for MySQL

## Related
- `batch-update-patterns.md`
- `upsert-on-conflict.md`
