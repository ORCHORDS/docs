# postgres-enum-patterns

**Issue:** Every schema has columns with a small closed set of values — status, kind, plan tier, event type. Postgres offers three ways to model them: native enum types (`CREATE TYPE`), lookup tables with a foreign key, or free text with a `CHECK` constraint. The choice looks cosmetic and gets made casually, then haunts the team: native enums need `ALTER TYPE` (a catalog DDL) to add values and cannot remove them at all, while lookup tables make every new value a data-only insert. Pick per column based on how the value set actually evolves, not on which looks tidier in an ERD.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The three options and their contracts

1. **Native enum type.** `CREATE TYPE order_status AS ENUM ('pending','paid','shipped')` gives a real type: 4 bytes on disk regardless of label length, rejects unknown values at parse/plan time, and displays as readable text. The value list lives in the system catalog and changes only via `ALTER TYPE`.
2. **Lookup table with FK.** A `order_statuses` table (code, label, sort_order, maybe metadata) plus a FK-validated column. Adding a value is an `INSERT`; the FK gives integrity; the table is the natural home for extra facts (display name, i18n, is_terminal flag, color) and is visible to every tool that can read a table.
3. **Text column plus CHECK constraint.** The value list lives in the DDL as `CHECK (status IN (...))`. No extra objects, values visible right in `\d`, but adding a value is an `ALTER TABLE` — a schema change and a lock-taking migration for what is conceptually data.

## Why lookup tables usually win

1. **New values are data, not schema.** The decisive argument (the Cybertec comparison and community consensus): business teams add statuses and categories constantly, and an `INSERT` deployable instantly beats a migration that must be reviewed, applied, and rolled forward. Data-only changes also do not require the migration role or lock the table.
2. **Values carry metadata eventually.** The moment someone asks for display labels, ordering, "which statuses count as active", or translated names, a lookup table has somewhere to put it; enums and CHECKs push that knowledge into application code, where it forks.
3. **Removal and deprecation are possible.** Native enum labels cannot be dropped or reordered (recreating the type is a full migration); a lookup row can be flagged inactive while historical rows keep referencing it, and FKs keep the story honest.
4. **Referential integrity across tables.** Several tables sharing one vocabulary (status on orders and on shipments) get one FK target instead of duplicated enum types or CHECK clauses that drift apart.
5. **Tooling friendliness.** ORMs, BI tools, and code generators read lookup tables naturally; native enums need per-language type mapping, and every new label is a codegen or mapping update in each consumer.

## When native enums are the right call

1. **Truly closed vocabularies.** Direction (`inbound`/`outbound`), boolean-like tri-states, protocol constants — sets that change as often as the schema itself changes. Here the enum's strictness is a feature: the compiler/parser and the schema agree, and no runtime row can invent a value.
2. **Compact and fast by construction.** An enum is 4 bytes whether the label is 6 or 60 characters, compares as its declaration order, and needs no join; a lookup table's joins are usually cheap but not free on very hot paths.
3. **Sort order semantics.** Enums sort in declaration order, not lexical order — `ORDER BY status` gives a natural pipeline order ('pending' before 'shipped') without a sort_order column. This is also a trap if declaration order is ever "wrong"; it cannot be changed without recreating the type.
4. **One vocabulary, one database.** If the values are internal to the DB (partition keys, job states consumed only by DB-side code), enum ergonomics beat a lookup table nobody else reads.

## Living with native enums (the pain points)

1. **Adding a value is `ALTER TYPE ... ADD VALUE`.** Since PG12 it can run inside a transaction block, but the new value cannot be used in the same transaction that added it — which breaks the common "add value and backfill/migrate data in one migration" pattern; split it into two migrations or guard with care. Many migration tools still wrap everything in one transaction.
2. **Never remove or reorder labels.** Dropping or renaming a label requires creating a new type, rewriting the column, and dropping the old type — a real migration with all the locking that entails. Design enums as append-only and deprecate in application logic instead.
3. **String comparisons do not do what people expect.** An enum is not text: `status::text` is needed for generic string handling, `enum_range()` is the way to list values, and literal casts (`'shipped'::order_status`) surprise application layers that bind parameters as text (most drivers handle it, some ORMs need type hints per column).
4. **Schema-level coupling.** Because the type lives in the catalog, every consumer (ORM entities, GraphQL enums, TS union types) must be updated in lockstep with the database change; a lookup table keeps the DB permissive while consumers catch up.

## Decision rules and hygiene

1. **Default to a lookup table when any of these hold:** the value list is owned by product/business logic, values may be added frequently, values need metadata or i18n, or multiple tables share the vocabulary.
2. **Default to a native enum when:** the set is closed and technical, changes only with schema redesign, and consumers all live close to the database.
3. **Prefer CHECK constraints rarely and deliberately:** small schemas, prototyping, or single-column one-off lists where a whole table feels heavy but the list truly is static.
4. **Whichever you choose, centralize it in code.** Generate the application-side union type/literal list from one source (the lookup table via codegen, or the enum via a migration-time reflection) instead of hand-maintaining a third copy in TypeScript; drift between DB values and code unions is guaranteed otherwise.
5. **Record the decision where the column is defined.** A one-line comment on the column ("lookup table because marketing adds tiers quarterly") prevents the next engineer from "simplifying" it into an enum and rediscovering `ALTER TYPE` in a deploy window.
