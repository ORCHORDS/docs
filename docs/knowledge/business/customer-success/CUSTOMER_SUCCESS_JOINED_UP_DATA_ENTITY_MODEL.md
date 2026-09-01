# Customer Success Joined-Up Data Entity Model

A single customer view does not come from buying one system; it comes from deciding, once and explicitly, what the entities are, how they relate, and which system holds the authoritative version of each attribute. Without those decisions, every team builds its own partial model — support thinks in contacts, billing thinks in contracts, customer success thinks in accounts — and joins produce doubled, split, or scrambled customers. This article defines the entity model behind a joined-up customer view and the survivorship rules that keep it coherent.

## Scope

Covers the conceptual and logical entity model for customer-success data: core entities (organization, contract/agreement, subscription/entitlement, contact/user, product capability, case, interaction, opportunity), their identifiers, and their relationships — plus the survivorship rules resolving conflicting attribute values across contributing systems. Applies to the design and periodic review of the joined view and its feeding mappings. Does not cover physical replication architecture, real-time streaming design, or the deduplication matching rules for joining support banks to CRM, which are governed separately; this article consumes that output.

## Workflow or implementation guidance

1. **Define core entities with boundaries and definitions.** Each entity gets a plain-language definition, boundary statement (what it is not), and owning system. The organization is the legal or operational customer; the subscription attaches to it; the contact attaches to the organization through employment or engagement, not through whichever system first recorded them. Written definitions prevent the slow slide where "account" means different things in different feeds.
2. **Assign one authoritative system per attribute.** For every attribute in the joined view — contract value, renewal date, industry, support tier, health score, owner — declare the single system of record. Attributes with no authoritative source are marked unsourced and excluded from decision use until sourced, rather than silently filled from wherever data happens to exist.
3. **Choose identifiers deliberately.** Each core entity carries a global, system-independent identifier minted by the joined-view layer, plus mappings to native identifiers in each contributing system. Joins flow through the mapping table; direct system-to-system identifier coupling is prohibited because it hard-codes someone else's key semantics into your model.
4. **Model relationships with cardinality made explicit.** One organization to many subscriptions, many contacts, many cases; subscription to product capabilities; contact to interactions. Ambiguous cardinalities (a person serving two customer organizations — consultants, shared service centers) get explicit resolution rules rather than an assumption of simplicity.
5. **Write survivorship rules per attribute, with provenance retained.** Conflicts resolve by declared precedence — authoritative system first, then recency, then completeness — and the joined record retains which source supplied each value and when, so any surprising value can be traced to its origin without forensic work.
6. **Version the model and the mappings.** The entity model, attribute authority matrix, and per-system mappings are versioned artifacts; a change to any of them is a change event with review, because downstream reports and scores shift meaning when the model shifts.
7. **Publish to consumers.** Teams building on the joined view consume published, documented entity services or datasets — not direct reads into the joining machinery — so the model can evolve without breaking every consumer simultaneously.
8. **Review on cadence.** Semiannually, review entity definitions against business reality (new sales motions, new product lines), audit attribute authority against system changes, and retire attributes no one consumes.

## Controls

- The attribute authority matrix is the single place precedence lives; code implementing survivorship is generated from or validated against it, not hand-written folklore.
- Every joined record is reconstructable: given the record, produce the contributing source records and the rules that produced each attribute value.
- The unsourced-attribute list is published; consumers can see which fields are decision-grade and which are convenience-only.
- Identifier mapping changes require dual-entry validation — a sample of mappings verified against both systems — before activation.
- Access to the joined view is role-based and field-level where attributes carry sensitivity, honoring the most restrictive source's rules for any derived field.

## Validation evidence

A sound joined-up model demonstrates: the entity definition document with boundaries; the attribute authority matrix with owning system per attribute; mapping tables with native-identifier coverage statistics per contributing system; survivorship provenance samples showing five conflicting attributes resolved and traced; the model and mapping version history with change records; and a consistency report — per-entity counts in the joined view reconciled against each source system's own totals with explained variances. A lineage drill-through on one randomly chosen customer, from joined record back to every source value, completes the demonstration.

## Failure modes and correction

- **Attribute authority erosion** (a source system quietly changes an attribute's meaning — a status field gains new values): detected by the value-distribution monitoring on feeds; freeze the attribute, reconcile with the source owner, and re-map with a version increment.
- **Identifier mapping corruption** (bulk remap merges distinct organizations): roll back to the prior mapping version, quantify affected downstream views, and require dual-entry validation on the corrected mapping.
- **Definitional drift** (teams extend an entity's meaning in local reports): detected in consumer reviews; correct by publishing the definition alongside the data and re-pointing the local report to a properly modeled entity.
- **Phantom completeness** (unsourced attributes silently populated from convenience sources): purge to null, restore the unsourced marking, and fix the mapping that filled it.

## Limitations

A logical model cannot resolve genuine business ambiguity — whether franchises are one customer or many is a commercial decision the model can only encode once made. Source systems retain their own semantics, and the joined view is only as current as its feeds. Complex corporate structures will always strain the organization entity, and honest modeling acknowledges partial coverage rather than forcing every record into a clean shape.

## Canonical sources

- [ISO/IEC 8000-110 Master data](https://www.iso.org/standard/78941.html) — master data exchange, attribute authority, and quality characteristics for a joined view.
- [NIST SP 800-61 Rev. 2](https://csrc.nist.gov/publications/detail/sp/800-61/rev-2/final) — controlled response and evidence-preservation structure applied to mapping-corruption events.

Confirm standard currency on iso.org before local adoption; local procedures should track the editions in force.
