# typescript-orm-patterns

**Issue:** Common patterns and pitfalls when using TypeScript ORMs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
TypeScript ORMs (Prisma, Drizzle, TypeORM, Kysely) each have distinct trade-offs for type safety, performance, and migration management.

## Pattern / Solution
```typescript
// Kysely: type-safe query builder (no magic)
const result = await db
  .selectFrom(''users'')
  .select([''id'', ''email''])
  .where(''deleted_at'', ''is'', null)
  .orderBy(''created_at'', ''desc'')
  .limit(20)
  .execute();

// Prisma: declarative, auto-complete heavy
const user = await prisma.user.findFirst({
  where: { email: { contains: ''@acme.com'' } },
  select: { id: true, email: true },
});

// Raw SQL escape hatch (always available)
const rows = await db.execute(sql`SELECT * FROM users WHERE id = ${userId}`);
```

## Gotchas
- TypeORM''s eager loading (`relations`) generates separate queries, not JOINs — N+1 risk
- Prisma doesn''t support all PostgreSQL types natively; use `Unsupported("")` for exotic types
- Always have a raw SQL escape hatch; no ORM covers every edge case

## Related
- `drizzle-orm-patterns.md`
- `n-plus-one-query-detection.md`
