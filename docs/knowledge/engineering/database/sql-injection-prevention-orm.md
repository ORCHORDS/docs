# sql-injection-prevention-orm

**Issue:** ORM escape hatches and raw query helpers reintroduce injection risk
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Developers drop to queryRaw or knex.raw with template literals, negating ORM protections.

## Pattern / Solution
Audit all raw, literal, unsafe usages. For Prisma use tagged template Prisma.sql. For Knex use knex.raw with parameterized form. For dynamic identifiers use a strict allowlist enum -- never user input.

## Gotchas
- Second-order injection: data stored from one user used as a query fragment later
- ORDER BY direction and column name cannot be parameterized; must use allowlist
- Stored procedures called via raw queries can contain injection if they build dynamic SQL internally

## Related
- parameterized-queries
- row-level-security
- column-level-security
