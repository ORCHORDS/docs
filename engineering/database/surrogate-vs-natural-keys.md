# surrogate-vs-natural-keys

**Issue:** Deciding between surrogate (generated) and natural (business) keys
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Natural keys like email or SSN seem convenient but change over time; surrogates are stable but opaque.

## Pattern / Solution
```sql
-- Surrogate key (preferred for most tables)
CREATE TABLE customers (
  id    BIGSERIAL PRIMARY KEY,
  email TEXT NOT NULL UNIQUE  -- natural key as UNIQUE, not PK
);

-- Natural key as PK (only when truly immutable and short)
CREATE TABLE currencies (
  code TEXT PRIMARY KEY CHECK (length(code) = 3),  -- ISO 4217
  name TEXT NOT NULL
);
```

## Gotchas
- Natural keys that "never change" often do (email, phone, even SSN get reassigned)
- Exposing surrogate integer IDs in URLs leaks business metrics
- Use natural keys as UNIQUE constraints, not PKs, to get both benefits

## Related
- `primary-key-strategies-uuid-vs-int.md`
- `foreign-key-constraints.md`
