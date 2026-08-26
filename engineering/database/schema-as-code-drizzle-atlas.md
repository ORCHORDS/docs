# schema-as-code-drizzle-atlas

## Symptom

Database schema lives in migration files that only describe the delta, not the desired state. Developers can't answer "what does the current schema look like?" without replaying every migration. No drift detection between code and database.

## Pattern / Solution

Schema-as-code tools maintain a declarative definition of the desired schema and detect drift:

### Drizzle Kit (ORM-integrated)
- Define schema in TypeScript, generate SQL migrations from changes
- `drizzle-kit push`: apply schema directly to DB (dev/fast iteration)
- `drizzle-kit generate`: create migration files (production/safe)
- `drizzle-kit studio`: visual schema explorer + browser

```typescript
// schema.ts — single source of truth
import { pgTable, uuid, varchar, timestamp, integer } from 'drizzle-orm/pg-core';

export const users = pgTable('users', {
  id: uuid('id').defaultRandom().primaryKey(),
  email: varchar('email', { length: 255 }).notNull().unique(),
  createdAt: timestamp('created_at').defaultNow().notNull(),
});

export const posts = pgTable('posts', {
  id: uuid('id').defaultRandom().primaryKey(),
  userId: uuid('user_id').references(() => users.id).notNull(),
  views: integer('views').default(0).notNull(),
});
```

```bash
npx drizzle-kit generate  # creates SQL migration from schema diff
npx drizzle-kit migrate   # applies migrations
npx drizzle-kit push      # syncs schema directly (dev only)
```

### Atlas (infrastructure-as-code for databases)
- Language-agnostic — reads HCL, SQL DDL, or ORM schemas
- `atlas migrate diff`: detects schema drift and generates migration
- `atlas migrate apply`: applies pending migrations with version tracking
- `atlas schema inspect`: reverse-engineer existing DB to declarative format
- CI integration: `atlas migrate lint` checks migrations for dangerous operations

```bash
atlas migrate diff create_posts \
  --dir "file://migrations" \
  --to "file://schema.sql" \
  --dev-url "docker://postgres/15/dev"
```

### Comparison with traditional tools

| Tool | Approach | Drift detection | CI lint |
|---|---|---|---|
| Drizzle Kit | TypeScript schema → SQL | Yes (push --dry-run) | Limited |
| Atlas | Declarative SQL/HCL | Yes (migrate diff) | Yes (migrate lint) |
| Flyway/Liquibase | Imperative migrations only | No | No |
| Prisma Migrate | schema.prisma → SQL | Yes (migrate status) | No |
| Squawk | Linter for .sql files | No | Yes (rules) |

## Gotchas

- `drizzle-kit push` bypasses migration history — only use in dev, never production.
- Atlas's `dev-url` requires a clean database instance for diffing — use Docker for this.
- Declarative tools can't express everything imperative ones can (e.g., data migrations with `UPDATE` statements). Use raw SQL for data backfills.
- Always review generated migrations before applying — auto-generated `DROP COLUMN` is data loss.
- Drizzle's `push` doesn't generate rollback SQL — if it breaks, you restore from backup.

## Related

- `database/backward-compatible-migrations.md`
- `database/migration-rollback-strategy.md`
- `database/flyway-liquibase-patterns.md`
- `database/prisma-migrations.md`
