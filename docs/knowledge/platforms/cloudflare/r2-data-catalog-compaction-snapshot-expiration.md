# R2 Data Catalog compaction and snapshot expiration

**Issue:** Iceberg ingestion can create many small files and an expanding snapshot history. R2 Data Catalog can compact files and expire snapshots automatically, but retention settings can remove time-travel and rollback points and delete data files no longer referenced by retained snapshots.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Measure file-count, file-size, query, metadata, and storage baselines before enabling maintenance.
- Select compaction scope explicitly: catalog level affects all tables, while table level limits the change.
- Set a target file size appropriate for the query engine and workload; treat the documented default as a starting point, not an invariant.
- Configure both maximum snapshot age and minimum snapshots to keep. Review the combined retention outcome against recovery objectives.
- Exclude or separately govern tables subject to legal hold, audit retention, reproducibility, or long time-travel requirements.
- Use a dedicated service credential with only required R2 storage and R2 Data Catalog permissions; rotate and audit it.
- Back up independently when recovery must outlive catalog snapshots.

## Implementation and tests

Enable maintenance on a non-production table first. Generate representative small files and snapshots, wait for maintenance, then verify table correctness, retained snapshot count, oldest retained recovery point, query performance, storage change, and engine compatibility. Exercise rollback before and after the expiration boundary.

Roll out table by table. Record the maintenance scope, target size, age threshold, minimum snapshot count, credential owner, approval, and rollback plan. Alert on maintenance failure and unexpected loss of recovery depth.

## Gotchas and applicability

Compaction rewrites data files and consumes billable processing; it is not mere metadata cleanup. Snapshot expiration removes old snapshots and unreferenced files, so it is not a backup. The age threshold and minimum-count guard work together; verify current Cloudflare behavior and Wrangler version before automation.

Retention law and contractual duties vary by data and jurisdiction. Obtain the appropriate records or legal review rather than treating this operational note as legal advice.

## Official sources

- [Cloudflare R2: Manage catalogs](https://developers.cloudflare.com/r2/data-catalog/manage-catalogs/)
- [Cloudflare changelog: R2 Data Catalog snapshot expiration](https://developers.cloudflare.com/changelog/post/2025-12-18-r2-data-catalog-snapshot-expiration/)
- [Cloudflare R2 Data Catalog pricing](https://developers.cloudflare.com/r2/data-catalog/platform/pricing/)
