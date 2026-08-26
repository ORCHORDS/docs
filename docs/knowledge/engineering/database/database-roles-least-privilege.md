# database-roles-least-privilege

**Issue:** Most applications connect to Postgres as the table owner, a superuser, or a single fat role with `ALL PRIVILEGES` — convenient, and it means every SQL injection, every ORM bug, and every compromised service can `DROP TABLE`, read every tenant's rows, or write to `pg_shadow`. Least-privilege role design fixes this by separating who owns objects, who migrates them, and who runs application queries — each with exactly the privileges that job needs. It costs a handful of `CREATE ROLE` statements and a `GRANT` discipline that survives new tables.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The role layout

1. **An owner role that never logs in.** One `NOLOGIN` role (e.g. `example_owner`) owns the database, schemas, tables, and sequences. Ownership is what grants DDL rights; keeping it out of application hands means the app physically cannot alter schema regardless of what an attacker injects.
2. **A runtime role with DML only.** `example_app LOGIN` receives `SELECT, INSERT, UPDATE, DELETE` on application tables — deliberately not `TRUNCATE`, not `REFERENCES`, not `CREATE`. Most request paths need no more than this; if a feature needs more, that is a design smell to justify in review, not a default.
3. **A migration role with DDL.** `example_migrate LOGIN` (owned by or member of the owner role) exists for migration tooling to apply DDL. It connects during deploys and closes; it is never the application's connection string, so a runtime compromise cannot drop columns between deploys.
4. **Optional read-only analytics role.** `example_read` with `SELECT` (plus `pg_stat_*` monitoring views as needed) for dashboards, humans, and CDC consumers; granting it costs nothing and removes the temptation to hand out the app role for "just one query".
5. **Superuser for break-glass only.** One admin credential in the secret manager, used with audit logging, never in config files and never in the app. Anything that runs as superuser cannot be audited as "the app did it".

## Grants that keep working

1. **`ALTER DEFAULT PRIVILEGES` is mandatory.** Grants to existing tables do not cover future ones; without `ALTER DEFAULT PRIVILEGES FOR ROLE example_owner IN SCHEMA app GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO example_app` (plus the analogous `USAGE ON SEQUENCES`), every migration silently produces tables the app gets permission-denied on — usually on the next deploy, in production.
2. **Sequences are the forgotten grant.** `INSERT` into a table with a `serial`/identity column needs `USAGE, SELECT` on its sequences; bake it into default privileges or the first bulk load fails confusingly.
3. **Revoke the public defaults.** `REVOKE CREATE ON SCHEMA public FROM PUBLIC` (Postgres 15+ already limits this; older clusters and restored ones still leak it) and `REVOKE ALL ON DATABASE example project FROM PUBLIC` where appropriate. Default-allow schemas are where unscoped objects accumulate.
4. **Grant schema `USAGE`, not ownership.** Runtime roles need `USAGE` on schemas to see anything inside; they never need `CREATE`, which would let them plant objects (and functions with nasty search_path behavior) in shared schemas.

## Why runtime and migration credentials must differ

1. **Blast radius of injection.** SQL injection through the app role is capped at row damage in application tables — serious, but recoverable from backups and immutable audit trails. Through the owner/migration role it is total: schema destruction, `COPY` of the credential tables, function backdoors.
2. **Migration tools hold DDL by design.** Flyway/Liquibase/drizzle-kit need DDL during deploy; the same connection string in the app process is privilege the app holds 24/7 for a need that exists 30 seconds per deploy.
3. **Separation is auditable.** With distinct roles, `pg_stat_activity` and `pgAudit` logs can prove whether a destructive statement ran from a deploy or from a request path — one query in a forensic timeline instead of guesswork.
4. **It composes with RLS.** Row-level security policies apply to the role that queries; an app role that doubles as owner is exempt (`FORCE ROW LEVEL SECURITY` aside), silently disabling tenant isolation.

## Rotation and secret handling

1. **Roles are the rotation unit.** Rotate `example_app`'s password on a schedule by `ALTER ROLE ... PASSWORD` and swapping the secret in the manager; ownership never changes hands during rotation, which is why the owner role design pays off operationally.
2. **No passwords in repo, compose files, or plain connection strings.** Environment-injected secrets from the vault only; a leaked repo should yield zero database credentials.
3. **Connections identify themselves.** Set `application_name` per service (and per pooler stanza) so grants, logs, and `pg_stat_activity` line up with actual consumers; debugging a role's behavior requires knowing which code holds it.

## Auditing and drift checks

1. **Query effective privileges, not memory.** Periodic checks with `has_table_privilege('example_app', t.oid, 'DELETE')` over `pg_class`, or simply `\dp`-style reviews in a scheduled job, catch privilege drift after manual hotfixes.
2. **Review role membership.** `pg_roles` membership (who is in `example_owner`?) drifts when humans "temporarily" add themselves during incidents; diff it weekly.
3. **Watch for the owner-role smell.** Objects owned by `postgres` or personal superusers inside the application schema are the leading indicator that the discipline broke; alert on ownership outside the owner role.
