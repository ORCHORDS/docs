# JSON Schema Draft 2020-12 Version Governance

## Purpose

JSON Schema is a vocabulary-based language for describing and validating JSON instances. Schema behavior depends on the selected dialect, supported vocabularies, and validator configuration, so “JSON Schema” alone is not a sufficient compatibility claim.

Producers and consumers should preserve the exact dialect identifier and verify behavior with representative instances.

## Current context and source status

The JSON Schema project lists **Draft 2020-12** as the current published draft and Draft 2019-09 as its predecessor. “Draft 2020-12” is a named JSON Schema specification release; it should not be represented as a final IETF RFC. The project repository also develops future specification text through IETF Internet-Draft work, whose revisions are temporary working documents rather than final standards.

Earlier releases such as Draft-07, Draft-06, and Draft-04 remain deployed. Their continued use does not make their keyword and reference semantics interchangeable with 2020-12.

## Dialect controls

1. Include and preserve the exact `$schema` URI in every independently published schema.
2. Record the validator product and version, enabled vocabularies, format policy, and strictness settings used for acceptance decisions.
3. Reject or quarantine schemas whose declared dialect is unsupported instead of silently interpreting them as a preferred dialect.
4. Keep `$id`, anchors, dynamic references, and resource boundaries stable unless the migration explicitly changes identifier resolution.
5. Evaluate vocabulary support, including whether optional vocabularies are implemented and whether `format` is annotation-only or assertion-enforcing in the selected environment.
6. Test schemas with valid and invalid representative instances. Meta-schema validation alone does not prove intended instance behavior.
7. Version generated schemas and downstream code artifacts together so evidence can be reproduced.

## Migration review

A migration between 2019-09 and 2020-12 should inventory vocabulary URIs, array applicators, dynamic references, identifier resolution, `unevaluatedProperties` or `unevaluatedItems`, and format handling. A keyword recognized by both tools can still have different operational treatment because of configuration or vocabulary support.

For embedded schemas, also record the host format's rules. OpenAPI or another container may select a JSON Schema dialect or impose additional constraints; the embedded schema cannot be governed solely by its appearance.

## Untrusted schemas

Schema evaluation may consume substantial CPU or memory, resolve references, or process attacker-controlled regular expressions. Apply document-size, depth, reference-count, cycle, evaluation-time, and regular-expression limits. Remote reference retrieval should use approved destinations and must not expose ambient credentials.

## Failure modes

- Omitting `$schema` lets different validators infer different dialects.
- Using a 2020-12 keyword with a Draft-07-only validator can cause rejection or silent misinterpretation.
- Treating the draft name as semantic versioning creates false compatibility assumptions.
- Assuming `format` always rejects invalid values ignores dialect and implementation policy.
- Validating only against a meta-schema misses application-specific instance behavior.
- Rewriting `$id` or anchors without reference tests can change resolution across a schema graph.

## Sources

- JSON Schema specification overview: https://json-schema.org/specification
- JSON Schema specification repository: https://github.com/json-schema-org/json-schema-spec

Sources were checked on September 1, 2026.

## Scope note

This article governs JSON Schema dialect selection and migration. It does not claim that a schema expresses the intended business rules or that a particular validator is conformant.
