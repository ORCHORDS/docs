# composite-keys

**Issue:** Using multi-column primary keys for junction and time-series tables
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Junction tables and certain domain models are naturally identified by a combination of columns, not a single surrogate key.

## Pattern / Solution
```sql
-- Junction table with composite PK
CREATE TABLE user_roles (
  user_id BIGINT NOT NULL REFERENCES users(id),
  role_id BIGINT NOT NULL REFERENCES roles(id),
  granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, role_id)
);

-- Time-series: device + timestamp composite PK
CREATE TABLE readings (
  device_id  BIGINT NOT NULL,
  recorded_at TIMESTAMPTZ NOT NULL,
  value      NUMERIC NOT NULL,
  PRIMARY KEY (device_id, recorded_at)
);
```

## Gotchas
- Composite PKs increase FK complexity — child tables must carry all PK columns
- Column order in the composite key matters for index scan efficiency (leading column first)
- ORMs sometimes struggle with composite PKs; may need explicit mapping

## Related
- `primary-key-strategies-uuid-vs-int.md`
- `composite-index-design.md`
