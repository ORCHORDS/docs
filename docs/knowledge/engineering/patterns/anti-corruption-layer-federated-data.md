# Anti Corruption Layer Federated Data

## Scope

This article covers the Anti-Corruption Layer (ACL) as defined in Domain-Driven Design — a translating boundary that prevents an external or legacy model from leaking into a bounded context — specialized for federated data estates, where several independently governed systems must be composed into one query or aggregation surface. Scope includes read-model federation across systems owned by different teams, ingestion of third-party data feeds whose schemas evolve without notice, and aggregation APIs that join partner data with internal data. It excludes simple passthrough proxies with no model translation (that is a facade) and excludes ETL pipelines whose output is a wholly owned copy governed by internal schema rules (once copied and governed, translation is finished and no runtime layer is needed).

## Workflow or implementation guidance

Design the ACL around three components in fixed order: a façade that exposes the internal model, a translator that maps external representations onto it, and an adapter that handles protocol and authentication. The critical design decision is authoring the internal model before studying any single source too deeply. Write the federated view in the consuming domain's language — a `CustomerRiskProfile` with fields the business actually reasons about — then write one translator per source system. If the internal model is instead reverse-engineered from the most powerful source, every other source will look broken and the layer becomes a patchwork of exceptions.

Translation rules deserve explicit engineering. Prefer a declarative mapping table (external field, internal field, transform, default) over scattered imperative code, because mappings are what change when a partner schema shifts, and a table can be diffed, reviewed, and tested as data. Version every external contract: each source carries a schema version in its metadata, and the translator registry keys on it, so an unannounced field rename produces a loud version-mismatch error instead of silent nulls. Where sources disagree about the same concept — differing date precisions, currency codes, country formats — normalize into the internal canonical form at the boundary and record the normalization in the returned record's provenance, so downstream consumers can audit what was converted.

For query federation, sequence the ACL as: authenticate against the source, translate the internal query into source-native terms, execute, then translate rows back through the same mapping table in reverse. Keep the two translation directions generated from one mapping definition where possible; hand-writing both invites divergence.

```ts
interface SourceContractV2 { /* partner's native shape */ }
interface RiskProfile { /* internal canonical model */ }

function translateProfile(src: SourceContractV2, provenance: string[]): RiskProfile {
  // mapping-table-driven conversion; unknown enum values are errors, never silently null
}
```

## Controls

Treat the ACL as a contract enforcement point with its own controls. Require a per-source conformance suite: fixture documents captured from the real source, versioned alongside the translator, asserting the exact internal output — any source schema change shows up as a suite failure with a diff, not as corrupted data downstream. Enforce an unknown-value policy: unmapped enumerations, unparsable dates, and out-of-range numbers must either reject the record to a quarantine path or carry an explicit `unmapped` marker; silent nulls are the corruption the layer exists to prevent. Maintain a source registry recording owner, schema version, refresh cadence, and SLA class for every federated source, so the federation's availability budget is a computed fact. Alert on translation-miss rates per source; a rising miss rate is the earliest observable symptom of an unannounced upstream schema change.

## Validation evidence

Validate the layer with round-trip and differential tests. Round-trip: translate a sampled set of real source records into the internal model and back, asserting semantic equivalence where the mapping is declared bijective; one-way information loss is expected, but undeclared loss is a defect. Differential: when replacing an older integration with the ACL, run old and new paths in parallel for a fixed window and compare outputs record-by-record, counting and classifying every mismatch — mismatches must each be explained by a documented mapping decision or fixed before cutover. Schema-shock drills validate resilience: replay historical captured fixtures from before each past schema change and confirm the translator fails closed with a clear version error. As production evidence, track translation-miss rate, quarantine rate, and per-source staleness against the registry's declared cadence; these three numbers on one dashboard are the ongoing proof the layer is functioning.

## Failure modes and correction

The classic failure is the anemic ACL: a thin proxy that renames fields but lets external identifiers, enum vocabularies, and nullability semantics pour into the core domain, so a partner's schema change breaks internal services directly. Correct it by auditing internal models for foreign identifiers and by moving their translation into the mapping table. The inverse failure is the omnipotent ACL, which absorbs business logic — deduplication rules, risk scoring, merge policies — until it becomes an unowned monolith; correct it by restricting the layer to translation and pushing decisions into the bounded context that owns them. A third failure is silent version drift, where a source adds optional fields that flow through as nulls for months until someone depends on them; correct it with strict schema validation that rejects undeclared fields at the boundary in non-production environments. A fourth is quarantine neglect, where rejected records accumulate with no owner and no reprocessing path; correct it by making quarantine a reviewed queue with an age alarm, not a landfill.

## Limitations

An ACL adds a serialization and translation hop to every federated read, which costs latency and can double failure domains — the layer itself becomes a critical dependency whose outage breaks the federation even when all sources are healthy. It cannot reconcile genuinely contradictory source semantics, such as two systems disagreeing about what a customer is; that is an organizational problem that surfaces as awkward mapping code and is only truly fixed by renegotiating context boundaries. Real-time federation through an ACL also inherits the weakest source's freshness and availability, so serving paths with strict latency budgets usually need a materialized projection refreshed through the same translators, which reintroduces eventual consistency. Finally, the pattern's discipline erodes under deadline pressure precisely because a quick passthrough always looks cheaper than a correct mapping — the controls above exist because the failure mode is convenient.

## Canonical sources

- Eric Evans — Domain-Driven Design: Tackling Complexity in the Heart of Software, Addison-Wesley, 2003 (Anti-Corruption Layer, Context Map patterns).
- Microsoft Azure Architecture Center — Anti-Corruption Layer pattern: https://learn.microsoft.com/en-us/azure/architecture/patterns/anti-corruption-layer
- Cloudflare Queues documentation (quarantine and retry plumbing for translating pipelines): https://developers.cloudflare.com/queues/
- Hohpe and Woolf — Enterprise Integration Patterns, Addison-Wesley, 2004 (Message Translator, Canonical Data Model).
