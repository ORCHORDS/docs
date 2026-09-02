# W3C Web of Things Thing Description JSON Schema Governance

## Purpose

The W3C Web of Things (WoT) Thing Description (TD) is a structured JSON-LD document that describes a thing's metadata, security, protocol bindings, interactions, and schema. The TD JSON Schema defines the structural and value constraints of a TD, enabling validation of TD documents against the specification. This article governs the application of the WoT TD JSON Schema so a project can author valid TDs and validate TDs received from other things or services.

## Scope

The TD JSON Schema applies to any WoT deployment using TDs. Within this knowledge base, the article covers the TD structure (title, security definitions, properties, actions, events, links, forms), the JSON Schema for TD validation, the JSON-LD context for semantic interpretation, and the documentation of TD authoring conventions. It does not cover the discovery mechanism (a separate specification).

## Workflow

1. Identify the things the project describes with TDs. Each thing should have a TD that captures the metadata needed for consumers.
3. Author the TDs using the WoT TD specification:
   - @context: the JSON-LD context that defines the vocabulary.
   - title: a human-readable name.
   - securityDefinitions and security: the security schemes the thing supports.
   - properties, actions, events: the interactions the thing offers.
   - forms: the protocol bindings (HTTP, MQTT, CoAP) for each interaction.
   - links: relationships to other things.
   - @type: the semantic type(s) using the chosen vocabulary.
4. Validate each TD against the WoT TD JSON Schema using a JSON Schema validator.
5. Document the project's TD authoring conventions:
   - The vocabulary used for @type (e.g., iot.schema.org, custom vocabulary).
   - The protocol bindings supported.
   - The security schemes required.
   - The version policy for TDs.
6. Maintain the TDs as the things change. Update TDs on each material change.

## Controls and evidence

TD controls include the documented authoring conventions, the validation results, the TD samples, and the version history. Each TD should be reviewable against the project's conventions and the WoTTD JSON Schema.

## Validation

Validation should confirm each TD is valid against the JSON Schema, the conventions are followed, the vocabulary is correct, and the protocol bindings match the thing's implementation. Sample-based testing across TDs confirms the conventions.

## Failure correction

Common failure modes: TDs are not validated against the schema (correct: validate each TD before publication); vocabulary is inconsistent (correct: adopt a single vocabulary for the project and enforce it); TDs do not match the thing's actual implementation (correct: align the TD with the implementation and review on changes); protocol bindings are incorrect (correct: verify each form's method and URL against the implementation); security schemes are not documented (correct: include the securityDefinitions and the chosen security).

## Limitations

The TD JSON Schema defines the structural and value constraints; it does not certify any specific TD. The schema does not address the semantics of the TD beyond the JSON-LD context; semantic correctness depends on the vocabulary used. The schema does not address the runtime behavior of the thing; that is governed by the implementation.

## Scope note

This article summarizes project-neutral platform use of the W3C Web of Things Thing Description JSON Schema. It does not assert any specific TD's conformance or claim any certification outcome.

## Canonical sources

- W3C Web of Things Thing Description 1.1: https://www.w3.org/TR/wot-thing-description11/
- W3C WoT TD JSON Schema: https://www.w3.org/TR/wot-thing-description11/#json-schema-for-td