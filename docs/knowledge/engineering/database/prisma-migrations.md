# prisma-migrations

**Issue:** Managing database schema with Prisma Migrate
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Prisma schema drift and migration failures in CI/production are common pain points.

## Pattern / Solution
```bash
# Development workflow
npx prisma migrate dev --name add_user_phone
# Creates migration SQL, applies it, regenerates client

# Production deploy (never use migrate dev in prod)
npx prisma migrate deploy

# Reset dev database
npx prisma migrate reset

# Check migration status
npx prisma migrate status

# Resolve failed migration
npx prisma migrate resolve --applied "20260811000000_add_user_phone"
```

```prisma
model User {
  id        Int      @id @default(autoincrement())
  email     String   @unique
  phone     String?
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}
```

## Gotchas
- `migrate dev` regenerates the client and can fail in CI — use `migrate deploy` there
- Prisma does not support all PostgreSQL features (e.g., partial indexes require raw SQL in migrations)
- `prisma db push` skips migration history — only use for prototyping

## Related
- `drizzle-orm-patterns.md`
- `schema-migrations-patterns.md`
