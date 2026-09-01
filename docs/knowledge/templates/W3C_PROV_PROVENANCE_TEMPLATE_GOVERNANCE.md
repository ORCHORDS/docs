# W3C PROV Provenance Template Governance

## Purpose

Provenance is metadata about how an artefact was produced: what entities were involved, what activities acted on them, and who or what was responsible. The PROV family of specifications published by the W3C defines a generic data model for provenance (PROV-DM), an OWL ontology for use with RDF (PROV-O), and a serialisation in PROV-N. A provenance template uses PROV to capture the lifecycle of an artefact in a form that is portable, queryable, and shareable across organisations.

This article provides a public, project-neutral method for governing a provenance template based on the W3C PROV recommendations. It does not assert compliance with any other provenance standard and does not replace the published specifications' normative text.

## Scope

The scope covers the three W3C PROV Recommendations: PROV-DM (the data model), PROV-O (the OWL ontology), and PROV-N (the linearisation syntax). It covers:

- the three core classes — `prov:Entity`, `prov:Activity`, and `prov:Agent` — and how they relate to each other through `prov:wasAttributedTo`, `prov:wasGeneratedBy`, `prov:used`, `prov:wasAssociatedWith`, `prov:wasDerivedFrom`, and `prov:actedOnBehalfOf`;
- the role of bundles (`prov:Bundle`) and named graphs for grouping provenance statements about a single derivation;
- the use of `prov:role` properties and `prov:Plan` to express planned activities and the policies that governed them;
- qualifiers and extensions, which carry additional information about a relationship without changing the core data model; and
- the integration of PROV with Dublin Core or other metadata vocabularies where broader metadata is required.

## Workflow

Designing and operating a governed PROV template proceeds through a sequence that ties provenance to the artefacts it describes:

1. **Decide the scope of the provenance statement.** Identify which entities, activities, and agents the template will describe for each derivation. A template that tries to record everything produces statements no one queries; one that records too little fails the use cases that need traceability.
2. **Model entity, activity, and agent per derivation.** For each artefact of interest, decide which entities (the inputs and outputs), which activity (the derivation step), and which agents (people, organisations, and software) participate. The PROV data model prescribes how they connect.
3. **Use bundles to group statements.** Group the statements about one derivation into a `prov:Bundle`, so a consumer can retrieve the derivation's provenance as a unit and distinguish it from statements about other derivations.
4. **Apply roles and plans.** Use `prov:role` properties to distinguish agents that played structurally distinct parts (for example, author and reviewer), and `prov:Plan` to declare the policy or procedure the activity followed.
5. **Constrain value vocabularies.** Where a property's value is meant to be drawn from a controlled vocabulary (for example, types of agents or activities), declare the vocabulary in the template and bind the property to it.
6. **Bind to a serialisation.** Encode the template's bindings in PROV-N, RDF/XML, or another RDF syntax. Pick the serialisation on the basis of tooling and reproducibility, and record the binding in the template.
7. **Validate.** Validate the serialisation for syntactic correctness and check that the relationships implied by PROV-DM are present — every derivation has at least one activity, every activity uses at least one entity and produces at least one entity, and every activity is associated with at least one agent.
8. **Publish and link.** Publish the provenance file alongside or as a signed extension of the artefact it describes, with a stable identifier for the bundle.

## Controls and evidence

Evidence that PROV template governance operates correctly includes:

- the template definition, recording the PROV classes used, the serialisation, the controlled vocabularies bound to properties, and the bundle structure;
- the identifier scheme for entities, activities, agents, and bundles, recorded as a stable URI policy;
- validation reports showing each published provenance file passes the syntactic and minimal relational checks;
- the controlled-vocabulary registries and the procedures for changing them;
- provenance retrieval tests demonstrating that each artefact's provenance bundle can be fetched and queried; and
- a change log for the template and for each bundle, since provenance statements are meaningful only as a record of derivation, not of subsequent change.

## Validation

A governed PROV template is validated by:

- syntactic validation of the serialisation against the chosen encoding (PROV-N or RDF/XML);
- model validation: every entity and activity is typed, every derivation traces back to an activity, every activity is associated with at least one agent, and attributes such as `prov:role` resolve to the declared vocabulary;
- bundle integrity: every bundle identifier is unique, and no statement appears outside a bundle unless intended to apply globally;
- cross-bundle checks where derivations span bundles: cross-references resolve, and consistent identifiers are used;
- round-trip validation: the same provenance can be reconstructed from the encoded bundle and from the log records that produced it; and
- query validation: the queries the template is designed to support (for example, "what entities were derived from X?" or "who was responsible for activity Y?") return the expected results.

## Failure correction

Common failure modes in PROV template governance include:

- **Provenance emitted as text, not data.** The corrective action is to model the elements as structured data and serialise the bundle mechanically.
- **Missing activity or agent associations.** The corrective action is to enforce the relational completeness checks at validation and reject incomplete bundles.
- **Identifier instability.** The corrective action is to mint URIs through a stable policy and to forbid unbinding rebinding identifiers across bundles.
- **Bundles leak between derivations.** The corrective action is to enforce bundle scoping and revalidate when boundaries change.
- **Vocabulary drift.** The corrective action is to govern the controlled vocabularies under change control and to record the version in each bundle.

## Limitations

PROV describes what happened; it does not prove that what happened was correct, complete, or authorised. Trust in provenance requires that the agents and tools that produced it are themselves trustworthy. PROV is a generic model: it does not include domain-specific concepts (for example, regulatory approvals or specific lifecycle stages), which are expressed as extensions and require their own governance. The recommendations define only the data model, ontology, and a serialisation; storage, query language, and tooling are external choices. Finally, PROV is not a substitute for logging or audit trails: it is a structured way to make those records interoperable, not a replacement for producing them.

## Canonical sources

- W3C — PROV-DM, The PROV Data Model (Recommendation, 30 April 2013): https://www.w3.org/TR/prov-dm/
- W3C — PROV-O, The PROV Ontology (Recommendation, 30 April 2013): https://www.w3.org/TR/prov-o/

## Scope note

This article describes project-neutral governance for PROV-based provenance templates. It does not assert conformance to PROV for any specific implementation and does not reproduce the normative content of the cited recommendations.
