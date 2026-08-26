# data-masking-anonymization

**Issue:** Developers and CI pipelines need realistic data volumes and shapes to catch real bugs, so teams snapshot production into staging — copying real names, emails, phone numbers, and health/financial attributes into environments with weaker access control. That single practice turns every staging credential leak and every contractor laptop into a reportable PII incident. The fix is a repeatable masking (or anonymization, or synthetic-data) pipeline that produces non-prod copies that are safe by construction, not by policy.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Know what you have before transforming it

1. **Inventory PII as schema metadata.** Maintain an explicit list of columns holding direct identifiers (email, phone, national ID), quasi-identifiers (zip + birthdate combos), and sensitive attributes (health, financial), reviewed each migration; masking that lives only in a script's memory misses the next added column.
2. **Scan for PII you don't know about.** Discovery tools (Microsoft Presidio, cloud scanners like Macie, or simple pattern/dictionary sweeps over `pg_stats` most-common-values) catch free-text columns and JSON blobs where emails and names leak incidentally.
3. **Classify by re-identification risk, not by column name.** A birthdate alone is weak; birthdate + zip + diagnosis is a named person (the classic Sweeney result). Quasi-identifier sets need generalization or suppression, not just pseudonymization.
4. **Decide per dataset: masking, pseudonymization, or synthetic.** Masking (irreversibly transform real values) for staging; pseudonymization (deterministic, reversible mapping in a vault) for debugging production issues under controlled access; synthetic generation for demos, tests, and vendors.

## Transformation strategies that actually protect

1. **Deterministic pseudonymization preserves joins.** Replacing `user_id`/`email` with keyed hashes (HMAC with a secret kept out of the dump) keeps referential integrity across tables while breaking the link to real people — the workhorse transform for shared-key datasets.
2. **Randomization breaks distribution only if done carefully.** Shuffling a column within the table preserves the value pool but can still re-identify rare values; for rare-sensitive combos, generalize (birth year instead of date, state instead of zip).
3. **Format-preserving masks keep code paths exercised.** Fake-but-valid emails, phone numbers matching the real country prefix, and valid-looking card-shaped strings let validation logic, exports, and PDF renderers run unchanged in staging.
4. **Nulling and suppression are legitimate.** Free-text columns (`support_notes`) are near-impossible to reliably scrub; nulling them in staging loses little test value and removes the riskiest data class.
5. **Redact JSON blobs explicitly.** JSONB columns need per-key transforms; a top-level type-preserving pass that only hashes scalar keys misses nested identifiers and leaks them wholesale.

## Tooling landscape (2025-2026)

1. **PostgreSQL Anonymizer (Dalibo).** The established open-source extension: declarative `SECURITY LABEL`-based masking strategies, dynamic anonymization (masked views over real data for unprivileged roles), and permanent anonymization of copies — the default starting point for self-hosted Postgres.
2. **Greenmask.** Newer open-source tool that transforms during logical dump/restore, producing masked clones without touching the source; well suited to scheduled "refresh staging from prod" jobs.
3. **Presidio (Microsoft).** Library/service for PII detection and anonymization in text and tabular data; the right layer when free-text fields must survive in a redacted form.
4. **Commercial synthetic data platforms.** Tonic, Gretel, and cloud-native equivalents generate statistically realistic fake data preserving schema, joins, and distributions — the strongest privacy guarantee (no real person's data at all) at commercial cost.
5. **pg_dump with a twist for small setups.** A restore into a scratch database plus SQL UPDATE transforms plus a dump of the scratch is a fine v0 pipeline; the point is that it be scripted and reviewed, never an ad-hoc copy.

## Pipeline and process controls

1. **Mask inside the trust boundary, export only safe artifacts.** The refresh job runs where production access already exists (same VPC/CI runner with prod creds) and only the masked dump leaves it; never pipe a raw prod dump through a developer workstation.
2. **Automate refresh on a schedule and on demand per PR.** A nightly masked refresh plus CI jobs that seed ephemeral databases from the masked snapshot keeps "realistic data" from ever meaning "real data".
3. **Verify with assertions, not eyeballs.** Post-refresh checks: zero rows matching real email/phone regexes, HMAC columns uniformly distributed, row counts and join cardinalities within tolerance of prod — a failing assertion fails the pipeline.
4. **Keep connection strings and secrets asymmetric.** Staging must not be able to reach production, and prod credentials must never appear in the masking pipeline's logs; the pipeline's own access is the new crown jewel and should be short-lived.
5. **Record the mapping (or provably don't).** If pseudonymization is reversible for debugging, the key-to-identity map lives in a tightly access-controlled vault with its own audit log; if masking is the policy, prove irreversibility by construction (one-way functions) rather than promise.
6. **Re-review after every schema change.** The pipeline reads its column list from metadata that migrations must update; a CI check that fails when a new column lacks a classification keeps the guarantees from rotting.
