# flyway-liquibase-patterns

**Issue:** Using Flyway and Liquibase for automated schema versioning
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Manual migration management fails at team scale — tools enforce ordering and track applied migrations.

## Pattern / Solution
```
# Flyway file naming
V1__initial_schema.sql
V2__add_users_table.sql
V2.1__add_email_index.sql  (subversions)
R__refresh_views.sql       (repeatable, hash-tracked)

# Flyway config (flyway.conf)
flyway.url=jdbc:postgresql://localhost/mydb
flyway.user=postgres
flyway.locations=filesystem:./migrations

# Run
flyway migrate
flyway info
flyway repair   # fix checksum mismatches

# Liquibase changeset (XML)
<changeSet id="1" author="dev">
  <addColumn tableName="users">
    <column name="phone" type="TEXT"/>
  </addColumn>
</changeSet>
```

## Gotchas
- Never edit a migration file after it has been applied — Flyway will reject it (checksum mismatch)
- Liquibase supports rollback changesets natively; Flyway undo requires paid license
- Store migration files in version control alongside application code

## Related
- `schema-migrations-patterns.md`
- `prisma-migrations.md`
