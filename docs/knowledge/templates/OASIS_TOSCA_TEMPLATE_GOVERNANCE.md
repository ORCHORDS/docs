# OASIS TOSCA Service Template Governance

## Purpose

The Topology and Orchestration Specification for Cloud Applications (TOSCA) defines a portable, machine-readable model for describing cloud workloads and their relationships. At the core of TOSCA is the service template: the unit of deployment that declares node types, relationship types, capability and requirement definitions, policies, inputs, and the substitution mappings that let a composition be reused as a single component.

This article provides a public, project-neutral method for governing a TOSCA service template — its type library, its profile constraints, its versioning, and its validation. It is project-neutral and does not assert conformance to any TOSCA profile for a specific implementation.

## Scope

The scope covers the TOSCA Simple Profile in YAML version 1.3, the OASIS Standard most commonly used for service templates, together with the TOSCA version 2.0 draft work that extends it. It covers:

- the service template's top-level sections: `tosca_definitions_version`, `metadata`, `description`, `imports`, `dsl_definitions`, `node_types`, `relationship_types`, `capability_types`, `data_types`, `interface_types`, `artifact_types`, `group_types`, `policy_types`, `topology_template`, and the substitution mapping;
- the type hierarchy, in which a type derives from a parent and inherits its properties, attributes, and requirements;
- the topology template's `node_templates`, `relationship_templates`, `inputs`, `outputs`, `policies`, `groups`, and `substitution_mappings`;
- the normative type library shipped with the profile; and
- the relationship between a template and the orchestrator profile chosen to run it.

The scope does not cover orchestrator-specific extensions or non-normative profiles published outside OASIS.

## Workflow

Designing and operating a governed TOSCA service template proceeds through a defined sequence:

1. **Declare the definitions version.** Set `tosca_definitions_version` to the exact profile and version the template targets (for example, `tosca_simple_yaml_1_3`). The value determines the grammar, the default type library, and which normative types are available without an import.
2. **Build a type library.** Define node types, relationship types, capability types, and policy types as reusable assets with declared properties, attributes, and interfaces. Types are versioned artefacts, owned and published centrally — not ad-hoc definitions embedded in each template.
3. **Import deliberately.** Each `import` names a file or URL with a type library. Record every import's source and version; an unpinned import makes the template's meaning depend on the state of an external resource.
4. **Compose the topology template.** Instantiate node templates from the type library, wire requirements to capabilities through relationship templates, and use substitution mappings where a composition is exposed as a single component.
5. **Declare inputs and outputs.** Define the inputs the deployment requires and the outputs it exposes, with types, defaults, and status (required or not). Inputs make a template reusable across environments; hard-coded values make it single-use.
6. **Attach policies and groups.** Use policy types (for example, placement, scaling, or security policies) to place constraints on node groups rather than embedding constraints in each node template.
7. **Validate before deployment.** Validate the template against the profile grammar and against the type library before any orchestrator sees it. Validation failures are corrected in the template, never by patching the generated runtime state.
8. **Version and publish.** Version the template and its type library together, so that a template's meaning is reproducible from the pair.

## Controls and evidence

Evidence that TOSCA template governance operates correctly includes:

- the service template source, under version control, with the profile version declared;
- the type library, published as a versioned artefact with an owner and a change log;
- the import manifest, listing each import's identifier, source, and version;
- validation output from a conformant parser, demonstrating zero grammar errors and reviewed warnings;
- the input contract, documenting each input's type, default, and status;
- deployment records linking a deployed topology to the exact template version and input values used; and
- the substitution mapping contract, where a composition is reused, documenting the exposed capabilities and requirements.

## Validation

A governed TOSCA service template is validated by:

- parsing against the declared `tosca_definitions_version` grammar;
- resolving every type reference against the imported type libraries, confirming the referenced version is the intended one;
- checking property constraints against declared types and allowed value ranges;
- verifying every requirement is satisfied by a matching capability in the topology or by the substitution mapping;
- checking the input contract covers every environment the template is deployed to; and
- performing a dry-run plan against a target orchestrator, where the profile supports it, to confirm the intended deployment actions before execution.

## Failure correction

Common failure modes in TOSCA template governance include:

- **Unpinned imports.** The corrective action is to pin each import to a versioned artefact and record the pin in the import manifest.
- **Type definitions embedded per template.** The corrective action is to extract them to the central type library and reference them by import.
- **Hard-coded environment values.** The corrective action is to promote them to typed inputs with defaults and to revalidate each environment's input set.
- **Requirements satisfied only incidentally.** The corrective action is to declare the required capability type explicitly and to fail validation when it is absent.
- **Templates that drift from deployed state.** The corrective action is to redeploy from the template rather than mutate live state, and to record the drift as a defect in the template or library.

## Limitations

TOSCA defines a template language and a normative type library, not a complete orchestration runtime. Deployment behaviour depends on the orchestrator and profile chosen, and portability across orchestrators is limited to what the chosen profiles support in common. The normative type library is intentionally small; domain-specific types must be supplied by an organisation's own library, and their quality governs the quality of the templates built on them. TOSCA version 2.0 work continues at OASIS, so templates written for 1.3 may require migration. Conformance to the grammar does not ensure that the described topology is operationally sound: correctness of the modelled architecture remains the author's responsibility.

## Canonical sources

- OASIS — TOSCA Simple Profile in YAML Version 1.3, OASIS Standard: https://docs.oasis-open.org/tosca/TOSCA-Simple-Profile-YAML/v1.3/os/TOSCA-Simple-Profile-YAML-v1.3-os.html
- OASIS — Topology and Orchestration Specification for Cloud Applications (TOSCA) Version 1.0, OASIS Standard: https://docs.oasis-open.org/tosca/TOSCA/v1.0/os/TOSCA-v1.0-os.html

## Scope note

This article describes project-neutral governance of TOSCA service templates. It does not assert conformance to any TOSCA profile, does not certify any orchestrator, and does not reproduce the normative content of the OASIS specifications cited.
