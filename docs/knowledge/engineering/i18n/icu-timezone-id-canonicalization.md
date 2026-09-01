# ICU Time Zone Identifier Canonicalization

Time zone identifiers drift. `Asia/Calcutta` was joined by `Asia/Kolkata`; `Pacific/Enderbury` became `Pacific/Kanton`; `US/Pacific` and other short forms were deprecated in favor of region-slash-city identifiers; and the IANA time zone database periodically renames or aliases zones for political and editorial reasons. ICU maintains its own canonicalization layer on top of IANA data, and mishandling it produces duplicate-zone bugs, broken cache keys, failed lookups after upgrades, and user-visible resets of saved preferences. This article covers how ICU canonicalizes zone identifiers, the difference between IANA canonical IDs and ICU canonical IDs, and safe engineering practice around them.

## Scope

This article addresses time zone identifier handling in ICU: `getCanonicalID`, the distinction between IANA and ICU canonicalization, legacy short IDs, the `tz` data version, zone equivalence classes, and the interactions with CLDR meta-zones for display names. It covers identifier lifecycle, storage, and migration. It does not cover DST rule computation, time zone conversion arithmetic, or formatting of offsets except where identifiers are involved.

## Workflow or implementation guidance

ICU holds time zone data derived from the IANA time zone database, plus its own alias table. Two canonicalization modes matter:

- **IANA canonicalization** maps an identifier to the "primary" IANA zone when one has replaced another (e.g., `Asia/Calcutta` → `Asia/Kolkata` under IANA's `backward` links).
- **ICU canonicalization** additionally folds zones ICU considers equivalent into a preferred ICU ID, which historically kept stable identifiers even when IANA renamed — the classic case being that ICU's canonical ID for `Asia/Calcutta` remained `Asia/Calcutta` for years after IANA promoted `Asia/Kolkata`, because ICU's canonical form tracked the ID used for data lookup rather than the IANA "primary" flag. `getCanonicalID` with the IANA flag returns both forms where they differ.

The distinction sounds academic until it bites: a system that stores canonical IDs using ICU's view while a partner system canonicalizes using IANA's view will disagree about `Asia/Calcutta`-class zones, and joins or deduplication by zone ID silently split or merge populations.

Practical workflow:

1. **Store what the user chose, verbatim, with a resolution timestamp.** A preference of `Asia/Calcutta` should be persisted as `Asia/Calcutta`, not silently rewritten at rest. Canonicalize at usage boundaries, so an alias rename upstream never destroys information.
2. **Canonicalize consistently at exactly one layer.** Choose the service that owns zone identity (usually the scheduling or notification service) and have every other system treat stored IDs as opaque. If two layers canonicalize with different ICU versions, the same stored value can produce two canonical outputs; pin ICU everywhere or canonicalize nowhere except the owner.
3. **Never generate short IDs (`PST`, `EST`, `CST`) as canonical output.** They are ambiguous (`CST` is China Standard, Central, or Cuba Standard Time depending on who you ask), deprecated as inputs, and ICU maps them via special tables. Accept them on input for legacy reasons, canonicalize on read.
4. **Treat unknown-ID failures as data events.** When a stored ID no longer resolves after an ICU/tzdata upgrade, log it, fall back via a mapping table (the old ID's last-known-good equivalent), and schedule repair. Do not silently default to UTC, which hides population-level mis-scheduling.
5. **Key caches by (ID, tz data version).** Zone rules change (DST law changes in various countries multiple times a year); a cache keyed by ID alone can serve pre-law-change offsets after an upgrade within the same process lifetime if data reloads are partial.
6. **Use CLDR meta-zones for display grouping.** Display names like "Pacific Time" come from meta-zone data (e.g., zones `America/Los_Angeles` map to meta-zone `America_Pacific`); if you build "all zones in Pacific Time" style lists, group by meta-zone rather than by offset, which varies with DST.

A worked example: a calendar product stores user zones. In 2022 a user picks `Pacific/Enderbury`; after a tzdata upgrade the IANA database links it to `Pacific/Kanton`. If the product re-canonicalized at rest during migration, historical audit rows referencing the old ID would now be ambiguous. By storing verbatim and canonicalizing at display/scheduling time through a single pinned ICU, both the old and new ID resolve to the same rules, and the audit trail stays honest.

Upgrade sequence recommendation: pin ICU; before upgrading, extract the ICU zone-ID table diff (old vs new version) in CI; for every removed/renamed ID, generate a mapping entry; deploy the upgrade; run a reconciliation job validating that every stored ID still resolves, mapping those that do not; only then flip the canonical output for new writes.

## Controls

- Pin ICU (and thereby tzdata) versions across all services in the platform; version skew between services is the root of split-brain zone identity.
- CI check: parse the zone table from the pinned ICU version and assert that every stored ID found in a production snapshot resolves; fail the build on any that do not, with the mapping-table update as the fix path.
- Persist user-chosen IDs verbatim plus a `chosen_at` timestamp; canonicalize only at compute boundaries.
- Ban short zone IDs in APIs by contract test: reject three-letter IDs on write, accept-and-map on read.
- Alert on canonicalization mismatches: log when input ID ≠ canonical ID at the boundary, and track the rate over time; a spike after an upgrade signals a rename wave needing comms or migration.

## Validation evidence

- ICU's zone ID handling, `getCanonicalID` semantics with the IANA flag, and alias behavior are documented in the ICU User Guide timezone chapters; the underlying identifier set derives from the IANA time zone database.
- CLDR meta-zone data for display names is specified in UTS #35 (LDML), published by the Unicode Consortium.
- A reproducible check: on a current ICU build, call canonicalization on `Asia/Calcutta`, `Asia/Kolkata`, `US/Pacific`, `Pacific/Enderbury`, and `PST`; the outputs demonstrate IANA-vs-ICU divergence on at least one of them and the folding of legacy short IDs — concrete evidence both canonicalization modes must be chosen deliberately.

## Failure modes and correction

- **Canonicalizing at rest during upgrades.** Symptom: audit rows lose their original meaning; user-visible zone labels flip overnight. Correct by storing verbatim and canonicalizing at use.
- **Split canonicalization across services.** Symptom: duplicate "zones" in analytics (Calcutta and Kolkata counted separately). Correct by centralizing identity to one service with one ICU version.
- **Silent UTC fallback.** Symptom: notifications fire at wrong hours for affected users after a rename. Correct by explicit mapping and repair jobs.
- **Short IDs as output.** Symptom: partners reject or misinterpret `CST`. Correct by emitting region-slash-city IDs only.
- **Cache keyed by ID only.** Symptom: stale offsets after tzdata refresh mid-process. Correct by including the data version in cache keys.

## Limitations

- Canonical ID choice ultimately reflects IANA editorial policy and ICU policy, both of which can change; perfect stability is unattainable, hence the verbatim-plus-mapping strategy.
- Zone equivalence (aliases) does not imply identical future rules in pathological cases; equivalence is a statement about the current data version.
- Meta-zone grouping smooths display but blurs zones with divergent DST histories; do not use it for legal-effective time determinations.
- Some platform runtimes ship their own zone data (operating system tzdata, JRE tzdb); consistency requires aligning those too, not just ICU.

## Canonical sources

- Unicode, ICU User Guide — Time Zones (zone IDs, canonicalization, tzdata versioning): https://unicode-org.github.io/icu/userguide/datetime/timezone/
- Unicode Consortium, UTS #35: Unicode Locale Data Markup Language (LDML) — time zone data and meta-zones: https://unicode.org/reports/tr35/
