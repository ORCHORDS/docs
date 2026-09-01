# Marketing Campaign Event Schema Governance

Campaign analytics only support honest measurement when the events behind the dashboards mean what their names claim. This article sets schema discipline for marketing campaign analytics events: how events are named, how their properties are documented, how versions evolve, and how breaking changes are controlled so that a report comparing two periods compares the same thing. Weak schema governance produces silent measurement drift, where a renamed property or a redefined enum quietly changes a conversion definition while the dashboard keeps printing the old label.

## Scope

This control covers the event schemas emitted by marketing-owned surfaces and systems: web properties, mobile applications, landing pages, email and SMS link handling, paid-media tagging, partner postbacks, and internal campaign tooling. It applies to client-side trackers, server-side emitters, customer-data-platform conventions, and any downstream warehouse view that marketing treats as authoritative for campaign reporting. It governs event names, property names, data types, enum values, units, timestamps, identifiers, and the metadata that binds an event definition to a published version.

It does not govern the truthfulness of the advertising itself, the legal validity of consent flags, or general data-retention policy; those are covered by separate controls. Where an event carries a claim-relevant fact, such as a displayed price or a discount deadline, this control governs the fidelity of the recorded value to what the consumer actually saw, not the compliance of the underlying offer.

## Workflow or implementation guidance

1. **Register before emit.** Every event a campaign may fire must exist in the schema registry with an owner, a plain-language description, and a stable name before any code ships that emits it. Unregistered events observed in production are treated as defects, not as free enrichment.
2. **Apply a fixed naming convention.** Names follow one enforced pattern, for example `object_action` in lowercase snake case with a small controlled vocabulary of objects (campaign, offer, page, form, subscription) and actions (viewed, started, completed, dismissed, converted). The vocabulary list is versioned and reviewed; synonyms such as `clicked` versus `clicked_link` are rejected at review rather than reconciled later.
3. **Define properties with types and units.** Each property declares its type, allowed range, unit, and whether it is required. Currency amounts carry a currency code property in ISO 4217 form; durations carry a unit suffix or a documented default; timestamps carry a documented timezone convention, normally UTC with an explicit offset.
4. **Version semantically.** Additive changes, such as a new optional property, increment the minor version. Any change that could alter interpretation of existing data, including renamed properties, changed enum values, changed units, or a new firing condition, is a major version and requires a new event name or an explicit version field carried on every event.
5. **Gate breaking changes.** A major-version change requires a migration plan: which consumers depend on the old shape, how long dual emission runs, when the old version is frozen, and how historical data remains interpretable. The registry records the deprecation date and the removal date, and downstream owners must acknowledge before removal proceeds.
6. **Bind schemas to releases.** The schema version active during each campaign flight window is recorded in the campaign's measurement record, so a spike or dip in a metric can be checked against schema changes before it is explained as consumer behavior.
7. **Audit continuously.** An automated conformance check samples incoming events against the registry and alerts on unknown event names, unknown properties, type mismatches, and enum violations. Drift is triaged weekly.

## Controls

- A single accountable schema owner maintains the registry; approvals require a second reviewer for major versions.
- Write access to the registry is restricted and logged; every change carries a rationale and a linked ticket.
- Event names, property names, and enum values are treated as public contracts inside the organization: changing them requires the same change-management rigor as an API change.
- Duplicate or near-duplicate events are consolidated at review, with the surviving definition documented and the deprecated alias mapped, because silent parallel events are the most common source of conflicting dashboards.
- Consent and privacy flags travel with the event definition so that suppression rules can be applied at ingestion, not reconstructed afterward.
- Partner and vendor postback events are mapped to internal schemas through an explicit mapping document that is versioned alongside the registry.

## Validation evidence

- Registry snapshots showing, for each event, the active version, owner, definition, and change history.
- Release notes binding each deployed tracker or emitter build to the schema versions it emits.
- Conformance-monitor output over a representative window: counts of conformant events, rejected events, and unknown names, with disposition of each anomaly.
- For every major-version migration: the migration ticket, consumer acknowledgment, dual-emission comparison report, and post-removal verification that historical queries still resolve.
- A periodic replay test in which a known user journey is executed in a test environment and the emitted payload is diffed against the registry definition.

## Failure modes and correction

Common failures include a renamed property that quietly nulls a warehouse column, an enum value added without a version bump, two teams emitting the same event name with different meanings, a firing condition changed inside an A/B test without a schema note, and partner postbacks mapped once and never revalidated after the partner changes its payload. The most damaging pattern is interpretive drift: the dashboard label stays constant while the event's meaning shifts, so quarter-over-quarter comparisons mislead.

Correction starts with containment: freeze the affected definition, quantify the contaminated date range using conformance logs and release history, and mark affected reports rather than quietly patching them. The schema defect is fixed in the registry first, then emitters are corrected and the fix is verified by replay. Historical data is re-interpreted through an explicit mapping or explicitly annotated as non-comparable. Recurrence triggers a harder gate: schema CI checks that fail builds emitting unregistered events.

## Limitations

This control improves measurement integrity; it does not certify that analytics are correct in an absolute sense, since a schema can be perfectly conformant to a wrong definition. It does not resolve disputes over which conversion definition the business should use. Third-party platforms that expose only proprietary event models are governed only at the mapping layer, and their undocumented changes can still cause drift that internal evidence detects but cannot prevent. The controlled vocabularies here are internal conventions, not industry standards, and partners may legitimately use different external schemas.

## Canonical sources

- **Primary authority 1 — W3C, JSON-LD 1.1 (structured data versioning and context discipline):** [https://www.w3.org/TR/json-ld11/](https://www.w3.org/TR/json-ld11/)
- **Primary authority 2 — Schema.org vocabulary release model:** [https://schema.org/docs/releases.html](https://schema.org/docs/releases.html)
- **Reference — Semantic Versioning 2.0.0 specification:** [https://semver.org/](https://semver.org/)
