# OASIS CMIS Content Repository Template Governance

## Purpose

The Content Management Interoperability Services (CMIS) specification defines a domain model and bindings for interacting with content repositories: repositories expose object types, documents, folders, relationships, policies, and queries through AtomPub, Browser (JSON), and Web Services bindings. CMIS makes a repository's type definitions the contract that client applications depend on.

This article provides a public, project-neutral method for governing a CMIS object-type template — the type definitions, property definitions, and constraints that make repository content predictable across repositories and clients. It is project-neutral and does not assert CMIS conformance for any specific repository.

## Scope

The scope covers the CMIS domain model defined by the OASIS CMIS 1.1 Specification and the CMIS 1.1 errata. It covers:

- the base object types: `cmis:document`, `cmis:folder`, `cmis:relationship`, `cmis:policy`, and `cmis:item`;
- the property definitions attached to types, including id, local name, display name, query name, data type, cardinality, updatability, requiredness, default value, open/closed choice constraints, and orderable and queryable flags;
- type mutability controls: whether a type is creatable, fileable, controllable (for policies, ACLs, and versions), and whether it can be used in a query;
- secondary types, which attach additional property definitions to primary objects;
- repository capabilities, which determine what a template can rely on (for example, whether the repository supports joins, multifiling, or specific versioning semantics); and
- the bindings through which type definitions and objects are exchanged.

## Workflow

Designing and operating a governed CMIS type template proceeds through a defined sequence:

1. **Survey repository capabilities.** A type template is only as good as the capabilities the repository exposes. Before designing types, read the repository information returned through the chosen binding and record the capability flags that matter — versioning capability, query capability, join support, Renditions, and multifiling. A template that assumes a capability the repository does not expose will fail at runtime.
2. **Derive from base types.** Define custom types by inheriting from the appropriate base type. A document-like object with content derives from `cmis:document`; a container derives from `cmis:folder`; an association derives from `cmis:relationship`. Inheritance determines which system properties and behaviours apply automatically.
3. **Define property definitions deliberately.** For each property, record the id, local name and query name, data type, cardinality, updatability, required flag, default value, and any choice constraint. Every property should serve a retrieval or governance purpose; properties that no query, retention rule, or rendering uses should be removed.
4. **Constrain choices.** Use open/closed choice constraints where a property must take values from a controlled list. A closed choice prevents the repository from accepting off-list values; an open choice permits extensions while still publishing the preferred values.
5. **Mark queryability and orderability.** Properties used in queries must be queryable; properties used for sorting must also be orderable. These flags govern whether the repository can satisfy the queries clients will actually issue.
6. **Apply secondary types for cross-cutting metadata.** Where a set of properties applies to several unrelated primary types, define them once as a secondary type and apply it where needed, rather than duplicating property definitions across types.
7. **Publish the type definitions.** Publish the type tree as a versioned artefact with an owner and a change log, so clients can code against a stable contract.
8. **Validate before deployment.** Validate the type definitions against the CMIS schema and against the repository's capability set before creation.

## Controls and evidence

Evidence that CMIS type governance operates correctly includes:

- the published type definitions, versioned with an owner and change log;
- the capability survey of each target repository, dated, with the capability flags recorded;
- a mapping of each property definition to the query, retention, or rendering requirement it serves;
- validation output confirming the type tree conforms to the CMIS schema and the property flags are consistent;
- client integration notes recording which types and properties each client depends on; and
- change records for each type modification, including whether existing objects required migration.

## Validation

A governed CMIS type template is validated by:

- schema validation of the type definitions against the CMIS 1.1 schema for the chosen binding;
- capability validation confirming each assumption made by the template is supported by each target repository;
- query testing: every query the clients are expected to issue runs against the defined types and returns the expected properties;
- constraint testing: closed-choice properties reject off-list values and required properties reject absent values;
- inheritance testing: derived types inherit the expected system properties and behaviours from their base type; and
- round-trip testing through each binding in use (AtomPub, Browser, Web Services) to confirm type definitions and property values survive serialisation.

## Failure correction

Common failure modes in CMIS type governance include:

- **Types that assume unsupported capabilities.** The corrective action is to record the capability survey, redesign the affected part of the template, or exclude the repository.
- **Ungoverned property proliferation.** The corrective action is to remove unused properties, version the type tree, and migrate existing objects where the removal is breaking.
- **Query names that collide or change.** The corrective action is to treat query names as immutable public identifiers and to require a new type version for any change.
- **Required properties added after content exists.** The corrective action is to backfill existing objects under change control before enabling the required flag, or to stage the property as optional first.
- **Choice constraints applied without a controlled vocabulary owner.** The corrective action is to record the governing vocabulary for each closed choice and to validate changes against it.

## Limitations

CMIS defines interoperability at the level of the domain model and bindings, not repository behaviour in full. Two conformant repositories can differ in capability flags, in query support, and in how they treat aspects the specification leaves open, so portability is bounded by the least capable repository in scope. CMIS does not define full-text search semantics, retention and legal hold, or records-management behaviour; those come from other specifications such as the records-management standards. Finally, CMIS type governance does not by itself secure content: access control is governed by ACLs and the repository's authorisation model, which must be governed separately.

## Canonical sources

- OASIS — Content Management Interoperability Services (CMIS) Version 1.1, OASIS Standard: https://docs.oasis-open.org/cmis/CMIS/v1.1/os/CMIS-v1.1-os.html
- OASIS — CMIS Version 1.1 errata: https://docs.oasis-open.org/cmis/CMIS/v1.1/errata01/os/CMIS-v1.1-errata01-os.html

## Scope note

This article describes project-neutral governance of CMIS object-type templates. It does not assert CMIS conformance for any specific repository or client and does not reproduce the normative content of the OASIS specification cited.
