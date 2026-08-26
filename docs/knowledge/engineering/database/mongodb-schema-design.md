# mongodb-schema-design

**Issue:** MongoDB schema flexibility leads to inconsistent documents and performance problems
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Documents with missing fields, inconsistent types, deeply nested arrays causing unbounded document growth. Queries requiring lookup (join) across many collections.

## Pattern / Solution
Embed related data that is always queried together and has bounded size. Reference (store ObjectId) for data queried independently or with unbounded growth. Schema validation via JSON Schema in collection validator. Pattern: embed one-to-few, reference one-to-many.

## Gotchas
- Document size limit is 16MB -- unbounded array embedding causes document growth issues
- lookup (join) is expensive; denormalize frequently queried data
- Avoid deeply nested paths (>3 levels); hard to index, update, and query

## Related
- mongodb-indexing-patterns
- normalization-denormalization-tradeoffs
- json-columns-patterns
