# W3C SHACL Shapes Constraint Language Template Governance

## Purpose

The W3C SHACL (Shapes Constraint Language) specification defines a language for validating RDF graphs against a set of conditions (shapes). SHACL is part of the W3C data validation ecosystem and complements SHACL Advanced Features (SPARQL-based constraints, rules) and SHACL JavaScript extensions. This article governs the application of SHACL as a template for validating RDF data the organization publishes or consumes.

## Scope

The specification applies to any organization that publishes or consumes RDF data subject to structural or semantic constraints. Within this knowledge base, the article covers the SHACL core concepts (shapes graph, data graph, target, constraint components, severity, validation report), the SHACL Advanced Features for SPARQL-based constraints, and the documentation of shapes. It does not cover the substantive domain modeling decisions; those are governed by the organization's domain expertise.

## Workflow

1. Identify the data graph(s) to be validated. The data graph is the RDF graph the shapes apply to.
2. Define the shapes graph:
   - For each class of resource to be constrained, define a NodeShape.
   - For each property constraint, define a PropertyShape with the appropriate Constraint Components (e.g., sh:datatype, sh:minCount, sh:maxCount, sh:pattern, sh:nodeKind).
   - Define the target: which resources in the data graph the shape applies to (target node, subject of, property of, class-based targets).
4. Apply severity levels (sh:Violation, sh:Warning, sh:Info) to distinguish must-fix constraints from advisory ones.
5. Use SHACL Advanced Features where the core is insufficient: SPARQL-based constraints for complex conditions, rules for derivations.
6. Run a SHACL validator against the data graph using the shapes graph. The validator produces a validation report.
7. Treat violations as defects; remediate the data graph or refine the shapes graph.

## Controls and evidence

SHACL controls include the shapes graph (the documented constraints), the validation reports (the evidence of validation), the remediation records, and the governance of the shapes graph (who can change it, how changes are reviewed). Each shape should be documented with its purpose, its author, its version, and the resources it constrains.

## Validation

Validation should confirm the shapes graph is well-formed SHACL, the validation runs produce correct reports, the constraints are correctly targeted, and the remediation process addresses violations. Re-running validation on data changes confirms the shapes remain accurate.

## Failure correction

Common failure modes: shapes are defined after the data rather than as part of the data model (corrective: define shapes during data model design); shapes are too permissive (corrective: review and tighten the constraints); validation runs are not gated into the publish process (corrective: integrate SHACL validation into the publication pipeline); shapes are not versioned (corrective: version the shapes graph and document changes).

## Limitations

SHACL is a validation language; it does not certify the data. The standard does not address the semantics of the data; the shapes express the constraints the organization chooses. SHACL is for RDF data; non-RDF data requires other validation tools.

## Scope note

This article summarizes project-neutral use of W3C SHACL as a template. It does not assert any specific data set's conformance or claim any certification outcome.

## Canonical sources

- W3C SHACL — Shapes Constraint Language: https://www.w3.org/TR/shacl/
- W3C SHACL — Advanced Features: https://www.w3.org/TR/shacl-af/