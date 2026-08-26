# json-columns-patterns

**Issue:** Storing and querying semi-structured data in JSON/JSONB columns
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Not all data fits a rigid schema; JSON columns handle optional, variable-shape payloads without nullable column sprawl.

## Pattern / Solution
```sql
-- Prefer JSONB over JSON (stored binary, supports indexing)
CREATE TABLE events (
  id      BIGSERIAL PRIMARY KEY,
  payload JSONB NOT NULL
);

-- GIN index for containment queries
CREATE INDEX idx_events_payload ON events USING GIN (payload);

-- Query operators
SELECT * FROM events WHERE payload @> ''{"type": "click"}'';
SELECT payload->>''user_id'' AS user_id FROM events;
SELECT * FROM events WHERE (payload->>''amount'')::numeric > 100;

-- Update nested key
UPDATE events SET payload = jsonb_set(payload, ''{status}'', ''"processed"'')
WHERE id = 1;
```

## Gotchas
- JSONB loses key insertion order and deduplicates keys
- Deeply nested JSONB queries bypass the query planner cost estimates
- Avoid storing data you need to filter/sort by in JSON — put it in real columns

## Related
- `array-columns-patterns.md`
- `partial-indexes.md`
