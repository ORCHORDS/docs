# data-pipeline-etl-testing

**Issue:** Data pipelines fail differently from services: nothing crashes, and no test goes red — the warehouse simply fills with silently wrong numbers. A schema drift upstream renames a column and nulls cascade into every dashboard; a late-arriving event duplicates a day of rows; a timezone conversion shifts revenue across month boundaries; a business definition (what counts as an active user) quietly diverges between two transform layers. Classic software tests don't map onto this world because the artifact under test is data, not behavior. The 2025 tooling consensus splits responsibilities: dbt tests for in-transformation assertions (uniqueness, not-null, referential integrity), dbt-expectations or Great Expectations (GX) for richer column-level contracts, and pipeline-level validation gates that block downstream publication when data quality regresses. The engineering problem is choosing assertions that catch real incidents without drowning analysts in false-positive checks, and wiring severity-gated checks into CI and orchestration so bad data stops propagating instead of corrupting everything downstream.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The test layers for pipelines

1. **Schema contracts.** Assert expected columns, types, and nullability on every model input and output. A schema check at each pipeline boundary (raw, staging, marts) catches upstream API and vendor-feed drift on arrival rather than three transformations later; tools encode this as explicit expectation suites or dbt model contracts.
2. **In-transformation assertions (dbt tests).** The dbt standard: unique on keys, not_null on critical columns, accepted_values on enums, relationships for referential integrity, attached directly to models so every dbt build re-verifies them. Generic tests on every model plus singular tests for business rules form the base layer most teams should reach first.
3. **Richer column contracts (dbt-expectations / GX).** When you need distributional and statistical checks — values between bounds, mean within tolerance of yesterday, regex shape on identifiers, column A greater than column B row-wise — dbt-expectations brings Great Expectations-style assertions inside dbt, while GX Core handles validation for pipelines outside dbt, with generated data docs acting as living documentation of expectations.
4. **Freshness and volume monitors.** Row-count anomaly checks (today within x percent of the trailing 7-day median, partition exists for every expected interval) and source freshness thresholds catch the classic silent failures: a cron job that half-ran, a feed that stopped sending, a filter that became too aggressive.
5. **End-to-end fixture runs in CI.** For each pipeline PR, run transforms against a small, version-controlled fixture dataset (seeded CSVs or generated via Faker-style factories) and assert the resulting mart tables against expected golden outputs. This is the closest analogue to unit tests and catches logic regressions that data-quality monitors on production data miss.

## Designing checks that don't cry wolf

1. **Severity tiers from day one.** Datadog's dbt guidance and the GX/dbt ecosystem converge on warn versus error severities: hard-fail only on contract violations (keys, nulls, schema) that corrupt downstream math; warn on statistical anomalies that need human triage. Pipelines where every check blocks train everyone to ignore them.
2. **Tolerance bands over point values.** Assert row counts and metrics against relative bands or trailing-window comparisons rather than exact numbers; production data is legitimately variable, and exact assertions fail every holiday and every marketing spike.
3. **Check ownership and metadata.** Tag every check with an owner and a runbook link (dbt meta fields or GX suite metadata) so pages route to the team that understands the domain; unowned checks are the ones that get muted, and muted checks are worse than absent ones because they create false confidence.
4. **False-positive budget.** Track per-check failure history; any check that fired without a real incident more than a couple of times per quarter gets recalibrated or demoted to warn. Treat check precision as a maintained property, not a set-and-forget.

## CI/CD and orchestration integration

1. **PR-stage slim runs.** Run the fixture-based build plus schema and contract tests on every pull request ( slim CI via dbt build --select state:modified+ against a PR-scoped target), keeping feedback under ten minutes while still catching breakage in every downstream model the change touches.
2. **Gate publication, not just notification.** In the orchestrator, make the mart-publication step conditional on validation success for the partition being written; quarantine failing partitions to a review schema instead of overwriting the table downstream consumers and BI tools read.
3. **Time-travel and late data.** Test explicitly for late-arriving and out-of-order events: backfill a fixture with a delayed event and assert idempotent merge logic (no duplicate rows, corrected aggregates). Idempotency of every incremental model is a test, not an assumption.
4. **Reproducible environments.** Pin dbt package versions, fixture data commits, and warehouse SQL dialect behavior; a pipeline test that depends on today's production snapshot is untestable. CI containers with the same engine (DuckDB/Postgres target for local parity) keep fixture runs deterministic.

## Semantic and business-rule testing

1. **Metric definition tests.** Where a metric is computed in multiple places (dashboard, export, API), assert one canonical implementation or derive all from a single tested model; silent divergence between definitions is the most common "the numbers don't match" incident.
2. **Dimensional integrity.** Referential tests on every fact-to-dimension join (no fact rows joining to null dimensions, grain declarations enforced) prevent fan-out duplication, which multiplies revenue silently and is invisible to row-count checks.
3. **Timezone and calendar boundaries.** Fixture tests that place events exactly at UTC midnight, month boundaries, and DST transitions verify partition assignment and period aggregation logic — the recurring class of "first-of-the-month numbers are wrong" bugs.
4. **PII and policy assertions.** Column checks that banned fields (raw emails, tokens) are absent or masked in marts turn data-handling policy into an executable contract, catching accidental exposure when someone adds a column mid-pipeline.
