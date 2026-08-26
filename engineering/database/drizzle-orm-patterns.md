# drizzle-orm-patterns

**Issue:** Schema definition and migration patterns with Drizzle ORM
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Drizzle offers type-safe SQL-like queries with schema-as-code and lightweight migrations.

## Pattern / Solution
```typescript
// schema.ts
import { pgTable, serial, text, timestamp } from ''drizzle-orm/pg-core'';

export const users = pgTable(''users'', {
  id: serial(''id'').primaryKey(),
  email: text(''email'').notNull().unique(),
  createdAt: timestamp(''created_at'', { withTimezone: true }).defaultNow().notNull(),
});

// Generate migration
// drizzle-kit generate:pg

// Apply migration
// drizzle-kit push:pg  (dev)
// drizzle-kit migrate  (prod)

// Querying
const result = await db
  .select({ id: users.id, email: users.email })
  .from(users)
  .where(eq(users.email, ''test@example.com''));
```

## Gotchas
- Drizzle migrations are plain SQL files — review them before applying
- Schema changes not reflected in Drizzle schema file won''t be in migrations
- Joins require explicit `.leftJoin()` / `.innerJoin()` — no automatic eager loading

## Related
- `prisma-migrations.md`
- `typescript-orm-patterns.md`
