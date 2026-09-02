# W3C RDF 1.2 Template Governance

## Purpose

The W3C RDF (Resource Description Framework) 1.2 specifications update the foundational RDF model, RDF syntaxes (Turtle, RDF/XML, RDFa, JSON-LD 1.1), and the SPARQL query language family. RDF 1.2 preserves the core RDF concepts (subject-predicate-object triples, IRI-denoted subjects, blank nodes, literals) and adds features aligned with the W3C's broader direction. This article governs the application of RDF 1.2 as a template for the organization's semantic data modeling, and the related syntaxes for publishing and exchanging RDF.

## Scope

The specifications apply to any organization that uses RDF for data modeling, data exchange, or knowledge representation. Within this knowledge base, the article covers the RDF 1.2 data model, the syntax choices (Turtle for human authoring; RDF/XML for legacy; RDFa for inline embedding; JSON-LD 1.1 for web-friendly exchange), the use of RDF vocabularies, and the documentation of the organization's RDF models. It does not cover SHACL validation (a separate W3C specification) or the SPARQL update features in depth.

## Workflow

1. Identify the data to be modeled in RDF. Define the entities (subjects), the relationships (predicates), and the values (objects) that the model needs to express.
2. Choose the syntaxes the organization will use for each context:
   - Turtle: human-authored files, version-controlled, suitable for small to medium datasets.
   - RDF/XML: legacy and tooling interop where XML is required.
   - JSON-LD 1.1: web-friendly JSON with a context; suitable for web APIs and Linked Data.
   - RDFa: inline embedding in HTML for publishing structured data on web pages.
3. Define or reuse RDF vocabularies. Reuse established vocabularies (Dublin Core, SKOS, schema.org, FOAF) where they fit; define custom vocabularies with stable IRIs and documentation only where needed.
4. Maintain the IRIs. Use stable, dereferenceable IRIs for subjects and predicates. Document IRI policy.
5. Apply SHACL or similar validation where the RDF must conform to a defined shape.
6. Publish the RDF data with appropriate content negotiation for human and machine consumers.

## Controls and evidence

RDF evidence includes the data files (in the chosen syntaxes), the vocabularies, the SHACL shapes (where used), the IRI policy, and the publication infrastructure. Each vocabulary term should have a documented definition with its IRI.

## Validation

Validation should confirm the RDF syntaxes are valid, the RDF model is consistent with the intended semantics, the vocabularies are reused where possible, IRIs are stable and dereferenceable, and the data conforms to the SHACL shapes (where used). Parsers and validators confirm the syntax; consistency checks confirm the semantics.

## Failure correction

Common failure modes: IRIs are unstable (corrective: adopt an IRI policy and use persistent IRIs); vocabularies are reinvented when established ones exist (corrective: search for existing vocabularies before defining new ones); RDF is published without content negotiation (corrective: deploy content negotiation for human and machine consumers); SHACL validation is missing (corrective: define SHACL shapes for the data and validate on publication).

## Limitations

RDF 1.2 is a specification family; it does not certify any specific data set or deployment. The standard does not prescribe the use of any particular ontology; the organization selects the vocabularies that fit its context. The standard does not address the storage or query of RDF data; those are governed by other tools and standards (SPARQL, triplestores).

## Scope note

This article summarizes project-neutral use of W3C RDF 1.2 as a template. It does not assert any specific RDF deployment's conformance or claim any certification outcome.

## Canonical sources

- W3C RDF 1.2 Concepts and Abstract Syntax: https://www.w3.org/TR/rdf12-concepts/
- W3C RDF 1.2 Turtle: https://www.w3.org/TR/rdf12-turtle/
- W3C JSON-LD 1.1: https://www.w3.org/TR/json-ld11/