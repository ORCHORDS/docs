# OASIS TOSCA Simple YAML 1.4 Governance

## Purpose

OASIS TOSCA (Topology and Orchestration Specification for Cloud Applications) defines a language for describing cloud applications and their orchestration. The Simple YAML profile 1.4 provides a human-readable syntax for TOSCA. Governance ensures that an organization describing cloud applications with TOSCA uses the Simple YAML profile consistently, that orchestration workflows match the topology, and that the profile is appropriate to the deployment context.

## Current context and source status

OASIS published TOSCA Simple Profile in YAML Version 1.4 as an OASIS Standard in 2023. The profile is a specialization of the TOSCA specification. Verify the current OASIS publications before treating any specific node type or relationship type as a current requirement.

## Governance workflow and controls

### 1. Apply TOSCA Simple YAML 1.4 syntax

Apply TOSCA Simple YAML 1.4 syntax for service templates. Use the defined node types (Compute, Container, SoftwareComponent, Network, Storage) and relationship types (Hosts, ConnectsTo, DependsOn).

### 2. Define service templates

Define service templates for each application topology. Include inputs, outputs, node templates, relationship templates, groups, and policies.

### 3. Use substitution mappings

Use substitution mappings to compose complex applications from simpler service templates. Document the composition.

### 4. Use node types

Define or import node types. Use the standard types where applicable. Define custom types for application-specific needs.

### 5. Define workflows

Define orchestration workflows that implement deployment, scaling, healing, and undeploy operations. Test workflows.

### 6. Document policies

Document policies (placement, scaling, security). Apply policies through the orchestration engine.

### 7. Validate service templates

Validate service templates using a TOSCA parser. Apply linting rules for the chosen profile.

## Validation and evidence

- Service template library.
- Workflow definitions.
- Validation reports.

## Failure correction

Common defects include invalid templates, missing substitution mappings, and untested workflows. Corrective actions include a template validation pipeline, a substitution mapping review, and a workflow testing schedule.

## Limitations

- TOSCA adoption is uneven across orchestration engines.
- Simple YAML 1.4 is a specialization; some features require the full TOSCA spec.
- Workflows can be complex; maintainable templates require discipline.
- Validation tooling is limited; manual review is required.

## Canonical sources

- OASIS, TOSCA Simple Profile in YAML Version 1.4, OASIS Standard, 2023.
- OASIS, TOSCA Cloud Application Topology and Orchestration Specification, current edition.

## Scope note

This article belongs to the reference leaf and cross-references the engineering leaf for orchestration, the platforms leaf for cloud orchestration, and the operations leaf for deployment automation.
