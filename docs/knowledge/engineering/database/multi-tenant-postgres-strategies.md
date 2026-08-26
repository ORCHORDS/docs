# multi-tenant-postgres-strategies

**Issue:** A B2B SaaS schema decision — database-per-tenant, schema-per-tenant, or one shared schema with a `tenant_id` discriminator — silently shapes migrations, connection pooling, backup granularity, noisy-neighbor behavior, and compliance answers for years. Picking shared tables "to keep it simple" leaks data the first time a query forgets `WHERE tenant_id = $1`; picking schema-per-tenant for isolation hits catalog bloat and migration sprawl at a few thousand tenants. The choice needs to be made with the tradeoffs explicit and revisited as tenant count and sizes diverge.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The three isolation models

1. **Shared schema, shared database (pooled).** Every table carries `tenant_id`; one migration, one connection pool, one backup, trivial cross-tenant analytics. The 2025 consensus (ClickHouse's engineering guide, AWS RLS writeups) treats this as the default for SaaS scaling past a few hundred tenants.
2. **Schema-per-tenant (silo-lite).** Same database, `tenant_goldman.projects` vs `tenant_acme.projects`; stronger logical isolation, per-tenant backup/restore via `pg_dump -n`, and per-tenant TTL is trivial. Costs: catalog bloat, no shared plan cache, migrations run N times, and `search_path` hazards under poolers.
3. **Database/cluster-per-tenant (full silo).** Maximum isolation and per-tenant tuning/upgrades, reserved for enterprise contracts or regulatory walls (region pinning, dedicated encryption keys); operationally it is N databases to monitor, patch, and back up, and cross-tenant product analytics becomes an ETL project.
4. **Hybrids are normal.** Small tenants pooled in the shared schema, a handful of whale/regulatory tenants on dedicated schemas or clusters, with the same application code parameterized over both — decide the routing once and make it data-driven, not code forks.

## Making the shared schema safe

1. **RLS as the enforcement floor.** Policies like `USING (tenant_id = current_setting('app.tenant_id')::bigint)` make the database refuse a missing-tenant query instead of trusting every code path; see the dedicated RLS article for policy mechanics.
2. **Force the session variable on every connection.** The `SET app.tenant_id` must be set per transaction/request (middleware or `SET LOCAL` inside the transaction) — a pooler reusing a connection without resetting it is the classic leak vector, so make unset-variable queries fail closed.
3. **Tenant_id first in every index.** Composite indexes should lead with `tenant_id` (`(tenant_id, created_at DESC)`), because virtually every query is scoped to one tenant; a global index on `created_at` alone serves almost no real query.
4. **Beware FORCE RLS and the table owner.** Table owners bypass RLS unless `FORCE ROW LEVEL SECURITY` is set; run the app as a non-owner role or force it explicitly, and test with the actual app role.
5. **Monitor noisy neighbors.** Per-tenant statement and IO accounting (log_line_prefix with the tenant, or per-tenant statement sampling) is the only way to answer "which tenant is killing the database" without guessing.

## Schema-per-tenant realities

1. **Thousands of schemas degrade the catalog.** Each schema multiplies catalog rows, slows `pg_dump`, bloats shared caches, and autovacuum works harder; practitioners consistently report pain in the low-thousands of tenants.
2. **Migrations become fleet operations.** A migration must apply across every schema, tracked per schema (a `schema_migrations` per tenant), with tooling for partial failure; a lock taken on 5,000 schemas in one transaction will time out somewhere.
3. **search_path is the attack and bug surface.** Setting `search_path = tenant_acme, public` per connection risks cross-tenant reads if unset, and symlink-style object shadowing if tenants can create objects; most teams wrap it in `SET LOCAL` with the tenant resolved from an authenticated token.
4. **Poolers complicate it further.** PgBouncer in transaction mode does not track session-level `SET search_path` correctly without `server_reset_query` discipline; this is the recurring footnote in every pooler-plus-schemas thread and a major reason teams retreat to shared schema.
5. **Per-tenant restore is the payoff.** `pg_dump -n tenant_x` restores one customer's data after their intern truncates a table — in a shared schema you need PITR for the whole database plus surgical row re-insertion, which is a materially worse incident.

## Choosing, and migrating between models

1. **Default shared schema + RLS unless a constraint forces otherwise.** Constraints that justify silos: contractual data isolation, regional data residency, wildly divergent tenant data volumes (one whale 1000x the rest), or per-tenant extension/config needs.
2. **Let tenant lifecycle drive the escape hatch early.** Design the `tenants` registry table with a `isolation` column from day one (default `shared`), so moving one tenant to its own schema later is a data move plus routing change, not a re-architecture.
3. **Migrating shared to schema-per-tenant is a one-way door per tenant.** Copy rows with `INSERT INTO tenant_x.t SELECT * FROM t WHERE tenant_id = x` in batches, dual-write or freeze the tenant briefly, then verify counts and drop the rows — rehearse on the largest tenant.
4. **Migrating schemas back to shared is harder.** It requires assigning global IDs (per-schema sequences collide; switch to UUIDs or offset ranges first) and re-parenting every FK — another reason to start pooled unless forced.
5. **Keep compliance answers data-driven.** "Delete all of tenant X's data" (GDPR offboarding) must be tested in whichever model you run: a `DELETE WHERE tenant_id` sweep with verification in shared mode, a schema drop in silo mode.
6. **Revisit at known thresholds.** Plan a design review when crossing ~500 schemas (catalog/pooler pressure), when the largest tenant exceeds ~10% of total writes (noisy neighbor), or when a contract demands physical isolation — not when the pain is already acute.
