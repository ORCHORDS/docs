# Dublin Core Metadata Template Governance

## Purpose

Dublin Core is a small, widely deployed metadata vocabulary originally designed for cross-domain resource discovery. The Dublin Core Metadata Initiative (DCMI) maintains the vocabulary and its supporting specifications, including the DCMI Metadata Terms, the DCMI Abstract Model, and the guidelines for Dublin Core Application Profiles (DCAP).

This article provides a public, project-neutral method for governing a metadata template built on Dublin Core: choosing elements, constraining value vocabularies, binding the template to a syntax, validating records, and correcting failures. It is project-neutral and does not assert DCMI conformance for any specific implementation.

## Scope

The scope covers the fifteen-element Dublin Core Metadata Element Set (ISO 15836-1:2017), the DCMI Metadata Terms refinements and encoding schemes (ISO 15836-2:2019), and the DCMI Abstract Model. It covers:

- the fifteen core elements: Title, Creator, Subject, Description, Publisher, Contributor, Date, Type, Format, Identifier, Source, Language, Relation, Coverage, and Rights;
- element refinements, which narrow the meaning of a core element without changing its scope;
- encoding schemes, which constrain the form of a value to a controlled vocabulary or syntax (for example, the DCMI Type Vocabulary or W3C date formats);
- the distinction between literal values and non-literal (URI-identified) values; and
- the DCMI Abstract Model's description model, where a described resource has properties whose values may themselves be resources.

The scope does not cover RDF serialisation details beyond what is needed to bind a template to a concrete syntax; those are defined by the RDF specifications maintained by W3C.

## Workflow

Designing and operating a Dublin Core-based template follows a profile-driven workflow:

1. **Determine discovery requirements.** Identify who needs to find the described resources, what queries they will issue, and what constraints the domain imposes. A template exists to make discovery predictable, not to be exhaustive.
2. **Select elements.** Choose the subset of the fifteen core elements the domain needs. Every selected element must serve a retrieval or management purpose; unused elements are omitted rather than left blank.
3. **Apply refinements sparingly.** Where a core element is too broad, apply a DCMI refinement (for example, replacing a generic Date with `created` or `issued`). A refinement must be justified by a real query need.
4. **Bind encoding schemes.** For each element or refinement, decide whether the value is a literal or a URI, and constrain the syntax using an encoding scheme. Common choices include W3CDTF for dates, the Internet Media Types registry for Format, and the DCMI Type Vocabulary for Type.
5. **Write a Dublin Core Application Profile.** Record, for each property: its label, its definition, its obligation (mandatory, recommended, or optional), its occurrence constraint, its allowed value types, and its governing encoding scheme. The DCAP documents both the vocabulary used and the local constraints applied.
6. **Bind to a syntax.** Express records in a concrete syntax — DC-Text, RDF/XML, or another RDF serialisation — and record the binding in the profile so that records can be parsed unambiguously.
7. **Validate and publish.** Validate each record against the profile before publication; reject or repair records that fail. Maintain the profile under version control so that validation rules are reproducible.

## Controls and evidence

Evidence that a Dublin Core template is governed correctly includes:

- the Dublin Core Application Profile, versioned and published, listing every property, obligation, and encoding scheme used;
- the namespace bindings for DCMI Metadata Terms, with the canonical URIs recorded;
- value-vocabulary registries for each controlled scheme, with their versions and provenance;
- validation rules derived mechanically from the profile, so that profile and validator cannot diverge;
- sample records demonstrating both a compliant record and the failure messages produced by non-compliant records; and
- a change log for the profile, including the reason for each change and the migration applied to existing records.

## Validation

A Dublin Core template is validated by:

- schema validation of the chosen syntax binding;
- obligation checks confirming mandatory properties are present and optional properties are either populated or absent;
- occurrence checks confirming repeat limits are respected;
- encoding-scheme checks confirming literal values conform to the declared syntax and non-literal values resolve to their governing vocabulary;
- consistency checks confirming refinements are used only where their parent element's scope applies; and
- retrieval testing with representative queries, confirming that records populated under the template are actually discoverable through the intended access paths.

## Failure correction

Common failure modes in Dublin Core template governance include:

- **Populating every element by default.** The corrective action is to reduce the template to the elements the domain actually queries, and to record the rationale in the profile.
- **Uncontrolled keywords in Subject.** The corrective action is to bind Subject to a controlled vocabulary or an encoding scheme and to validate values against it.
- **Inconsistent Date formats.** The corrective action is to bind Date to the W3CDTF encoding scheme and reject records with non-conforming literals.
- **Literal values where URIs are required.** The corrective action is to convert literals to vocabulary URIs where the profile declares a non-literal value, and to repair affected records under change control.
- **Profile and validator divergence.** The corrective action is to generate validation rules from the profile so the two cannot drift.

## Limitations

The fifteen-element set is deliberately minimal. It supports resource discovery well, but it does not carry the administrative, structural, or preservation metadata that fuller frameworks such as PREMIS or MODS provide. Dublin Core is domain-neutral, so domain-specific semantics require an application profile; without one, records remain interoperable only at the level of the core elements. DCMI terms carry no inherent trust: an Identifier value is only as reliable as the minting authority that issued it. Finally, DCMI specifications are maintained as living documents; a template that cites them must record the version and date on which it was based.

## Canonical sources

- DCMI — DCMI Metadata Terms: https://www.dublincore.org/specifications/dublin-core/dcmi-terms/
- ISO — ISO 15836-1:2017, Information and documentation — The Dublin Core metadata element set — Part 1: Core elements: https://www.iso.org/standard/71339.html

## Scope note

This article describes project-neutral governance of a metadata template built on the Dublin Core vocabulary. It does not assert conformance to DCMI specifications for any specific implementation and does not reproduce the normative definitions of the cited specifications.
