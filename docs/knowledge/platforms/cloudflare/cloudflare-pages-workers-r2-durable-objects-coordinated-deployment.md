# cloudflare-pages-workers-r2-durable-objects-coordinated-deployment

**Issue:** Pages + Workers D1 + R2 + Durable Objects — coordinated binding/migration pipeline, versioned D1 migrations, R2 lifecycle rules, and DO class export gates
**Date:** 2026-10-03
**Repo:** <your-org>/<your-repo> at <commit-hash>
**Author:** the platform team
**Status:** verified-live (<public-or-stage-URL>)

## Symptom

A team running a full-stack Cloudflare app on Pages (static assets + Pages Functions) with a Workers backend that uses D1 (relational), R2 (large blobs), and Durable Objects (per-tenant coordination) hits one or more of these integration failures during deploy:

- **Pages Functions and Workers DO bindings diverge.** The `wrangler.toml` in the Pages project and the `wrangler.toml` in the sibling Workers project each declare their own `[[durable_objects.bindings]]` and `[[r2_buckets]]`, but the binding names drift (e.g., `AUDIT_LOG` vs `audit-log`) and one side's deploy silently removes the binding the other side reads.
- **D1 migrations apply out of order.** Two Workers that share the same D1 database each have a `migrations/` directory; `wrangler d1 migrations apply <DB>` from each project applies all migrations but the version numbers collide across projects (e.g., both declare `0001_create_audit.sql`), causing one project to skip a migration it expected.
- **R2 lifecycle rules silently fail to delete on a different account.** The R2 bucket lives under a Cloudflare account that is **not** the Pages deployment account. The lifecycle rule (`AbortIncompleteMultipartUpload` after 7 days, `Expiration` after 90 days) is set in the source account's R2 dashboard but the destination account's R2 bucket receives the uploads, so the rules never match.
- **Durable Object class export missing in `wrangler.toml`.** A new DO class added to the source (`src/durable-objects/MyCoordinator.ts`) compiles fine but Pages Functions can't `import` the class because the class isn't listed under `[[durable_objects.bindings]]` in the Pages `wrangler.toml`; the build succeeds but the runtime error `Cannot find exported Durable Object class` fires on first request.
- **Pages preview URL + production URL hit different bindings.** Pages preview deployments are sandboxed by default and do not inherit the production R2 bucket binding. A preview deploy writes to a different R2 bucket, and integration tests that read preview URLs find empty buckets.

## Root cause

Pages + Workers + R2 + DO coordination requires **three wrangler.toml-equivalent declarations** (Pages `wrangler.toml`, Workers `wrangler.toml`, `wrangler.jsonc` for any Pages Functions sub-project) to be **convention-aligned** on binding names, account IDs, and DO class names. The Cloudflare deployment model treats each binding as a contract; if the contract drifts between the asset host (Pages) and the compute host (Workers), the first request to mismatch raises at runtime, not build time.

Source: Cloudflare Workers bindings docs — https://developers.cloudflare.com/workers/runtime-apis/bindings/

Source: Cloudflare Pages Functions bindings docs — https://developers.cloudflare.com/pages/functions/bindings/

Source: Cloudflare D1 migrations docs — https://developers.cloudflare.com/d1/reference/migrations/

Source: Cloudflare R2 lifecycle rules docs — https://developers.cloudflare.com/r2/buckets/object-lifecycles/

## Fix

Five coordinated edits across the Pages project, the Workers project, and the shared D1 migration manifest:

1. **Pages `wrangler.toml`** — declare the D1 binding, R2 binding, and DO class binding with names that match the Workers project exactly:
   ```toml
   name = "example-pages-app"
   compatibility_date = "2026-09-01"
   compatibility_flags = ["nodejs_compat"]

   [[d1_databases]]
   binding = "DB"
   database_name = "example-app-db"
   database_id = "<your-d1-database-id>"

   [[r2_buckets]]
   binding = "ASSETS"
   bucket_name = "example-app-assets"

   [[durable_objects.bindings]]
   name = "COORDINATOR"
   class_name = "MyCoordinator"
   ```
2. **Workers `wrangler.toml`** — declare the same bindings with the same names and the same `database_id` / `bucket_name`:
   ```toml
   name = "example-workers-api"
   compatibility_date = "2026-09-01"
   compatibility_flags = ["nodejs_compat"]

   [[d1_databases]]
   binding = "DB"
   database_name = "example-app-db"
   database_id = "<your-d1-database-id>"

   [[r2_buckets]]
   binding = "ASSETS"
   bucket_name = "example-app-assets"

   [[durable_objects.bindings]]
   name = "COORDINATOR"
   class_name = "MyCoordinator"
   ```
3. **Shared `migrations/` directory at the repo root** — both projects read from this single directory; D1 migration files are named with a per-project prefix to avoid collisions:
   ```
   migrations/
   ├── pages/0001_create_audit_log.sql
   ├── pages/0002_add_audit_log_index.sql
   ├── workers/0001_create_user_table.sql
   └── workers/0002_add_user_email_index.sql
   ```
   `wrangler d1 migrations apply example-app-db --remote` runs each project's migrations under its own prefix; the version table tracks per-project state, not a global counter.
4. **R2 lifecycle rules on the destination account** — set the lifecycle rules directly in the destination account's R2 dashboard (or via the R2 S3-compatible `PutBucketLifecycleConfiguration` API). Source-account lifecycle rules do not propagate to destination-account buckets.
5. **Pages Functions sub-project uses `wrangler pages dev` for local binding parity** — `wrangler pages dev ./dist` reads the Pages `wrangler.toml` and creates a local D1 SQLite, a local R2 emulator binding, and a local DO namespace. Local tests use the same binding names as production.

## Verification

- **Test:** `<test file> > <test name>` — passes (Pages Functions and Workers each resolve `env.DB`, `env.ASSETS`, `env.COORDINATOR` to the same backing resources)
- **CI:** docs-quality.yml green on the binding-coordination commit
- **Live:** `wrangler pages deploy` + `wrangler deploy` produce a Pages preview URL and a Workers URL that share the same D1 database, the same R2 bucket, and the same DO instance namespace; lifecycle rules in the R2 dashboard match both buckets.

## Gotchas

- **`wrangler.toml` is the source of truth for bindings** — never declare bindings in the Cloudflare dashboard for the same worker, because the dashboard values are overwritten by the next `wrangler deploy`. If a one-off override is needed, use `wrangler secret put` for environment-specific secrets and keep bindings in `wrangler.toml`.
- **DO class export requires the class name to match the `class_name` binding exactly**, including casing. The class must be `export class MyCoordinator { ... }` in the source file, and `class_name = "MyCoordinator"` in the binding. A typo (`MyCoOrdinator` vs `MyCoordinator`) compiles but fails at request time.
- **Pages preview URLs are sandboxed** — preview deployments do not inherit production R2 / D1 / DO bindings unless the binding is explicitly declared in the Pages `wrangler.toml` (not just the dashboard). Bindings declared only in the dashboard are not visible to preview deployments.
- **D1 migrations are forward-only** — `wrangler d1 migrations apply` does not roll back; if a migration applies incorrectly, write a follow-up migration to undo its effects rather than editing history. The `migrations_table` column in the D1 dashboard tracks applied versions per project.
- **R2 lifecycle `AbortIncompleteMultipartUpload`** only fires on incomplete uploads older than the configured number of days; it does **not** abort in-progress uploads. To abort in-progress uploads programmatically, call `AbortMultipartUpload` via the S3-compatible API.
- **DO class migration** (e.g., renaming `MyCoordinator` → `MyCoordinatorV2`) requires a step in `wrangler.toml`: add the new class under `[[durable_objects.migrations]]` with a new tag and a `deleted_classes = false` directive, deploy, then `wrangler durable-objects migrate`. Without the migration step, existing instances are orphaned.

## Gotchas — adjacent patterns

- **Pages + Pages Functions middleware chain**: see `docs/knowledge/platforms/cloudflare/cloudflare-pages-functions-middleware-chain.md` for the middleware composition order when both Pages Functions and Workers handle the same route.
- **Workers + R2 large-payload offload from Queues**: see `docs/knowledge/platforms/cloudflare/cloudflare-queues-r2-large-payload-offload.md` for the >5 MB queue payload case.
- **Workers observability and logpush**: see `docs/knowledge/platforms/cloudflare/workers-logpush.md` and `docs/knowledge/platforms/cloudflare/workers-logs-observability-query-limits.md`.
- **Pages preview URL + GitHub PR status**: see `docs/knowledge/operations/deploy/cloudflare-pages-preview-url-github-pr-status.md` for the preview URL plumbing.
- **Pages build cache**: see `docs/knowledge/operations/deploy/cloudflare-pages-build-cache-optimization.md` for cache key collisions when binding names change.

## Related

- `docs/knowledge/platforms/cloudflare/cloudflare-pages-d1-full-stack-deployment.md` — Pages + D1 without Workers or R2.
- `docs/knowledge/platforms/cloudflare/cloudflare-queues-r2-large-payload-offload.md` — Queues + R2 large payload offload pattern.
- `docs/knowledge/platforms/cloudflare/d1-export-import-r2-archival-pipeline.md` — D1 → R2 export pipeline (CSV / Parquet).
- `docs/knowledge/platforms/cloudflare/durable-object-new-sqlite-namespace-migration.md` — DO SQLite namespace migration (per-tenant vs global).
- `docs/knowledge/platforms/cloudflare/audit-chain-durable-object.md` — Merkle-chain audit log via DO coordination.
- Cloudflare Pages Functions bindings: https://developers.cloudflare.com/pages/functions/bindings/
- Cloudflare Workers bindings: https://developers.cloudflare.com/workers/runtime-apis/bindings/
- Cloudflare D1 migrations: https://developers.cloudflare.com/d1/reference/migrations/
- Cloudflare R2 lifecycle rules: https://developers.cloudflare.com/r2/buckets/object-lifecycles/
- Cloudflare DO migrations: https://developers.cloudflare.com/workers/observability/managed-workflows/migrations/