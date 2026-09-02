# OASIS TOSCA Simple Profile in YAML Cloud Template Governance

## Purpose

OASIS TOSCA (Topology and Orchestration Specification for Cloud Applications) defines a language for describing cloud application topologies and their orchestration. The TOSCA Simple Profile in YAML provides a YAML-based syntax for expressing node types, relationship types, groups, policies, and workflow activities, enabling portable cloud application templates that can be deployed on any conforming orchestrator. This article governs the application of the TOSCA Simple Profile in YAML as a template for designing portable cloud application deployments.

## Scope

The specification applies to any organization that designs cloud application templates intended for portability. Within this knowledge base, the article covers the TOSCA Simple Profile structure (topology template, node templates, relationship templates, groups, policies, inputs, outputs, workflow activities), the YAML syntax, the use of node types and relationship types, and the documentation of the templates. It does not cover a specific orchestrator's implementation; readers should consult the orchestrator documentation.

## Workflow

1. Identify the application to be described in TOSCA: the components, the connections, the policies, and the lifecycle operations.
2. Define or select the node types for each component (compute, network, storage, application, middleware) and the relationship types for each connection (hosted on, connects to, attaches to, depends on).
3. Express the application topology in YAML using the TOSCA Simple Profile structure:
   - topology_template: the container for the application description.
   - node_templates: instances of node types.
   - relationship_templates: instances of relationship types between nodes.
   - groups: sets of nodes that share characteristics or policies.
   - policies: constraints on placement, scaling, security, or other aspects.
   - inputs and outputs: parameters passed in and results returned by the template.
4. Define the workflow activities: the create, configure, start, stop, and delete operations on nodes. Workflow activities may use the standard TOSCA workflow primitives or implement custom operations.
5. Validate the YAML against the TOSCA Simple Profile specification. Use a TOSCA parser/validator.
6. Deploy the template on a conforming orchestrator. Capture deployment results and any deviations.

## Controls and evidence

TOSCA template evidence includes the YAML template, the node and relationship type definitions, the workflow definitions, the validation results, and the deployment records. Each template should be reviewable against the TOSCA Simple Profile specification.

## Validation

Validation should confirm the YAML is valid TOSCA, the template deploys correctly on a conforming orchestrator, the workflow activities work as expected, and the policies are applied. Sample-based testing across templates confirms the design.

## Failure correction

Common failure modes: node types are defined as one-off rather than reusable (correct: define reusable types and reference them); policies are not applied or are ambiguous (correct: specify the policies clearly using the TOSCA policy model); workflow activities are missing or wrong (correct: implement the workflow activities using the TOSCA workflow primitives or custom implementations); templates are not validated (correct: validate against the TOSCA specification and test on the target orchestrator before production).

## Limitations

TOSCA is a template language; it does not certify any orchestrator. The standard does not guarantee portability across all orchestrators; orchestrators may have different interpretations of the specification. Complex workflows may need additional tooling; the TOSCA workflow primitives are intentionally limited.

## Scope note

This article summarizes project-neutral platform use of OASIS TOSCA Simple Profile in YAML. It does not assert any specific template's conformance or claim any certification outcome.

## Canonical sources

- OASIS — TOSCA Simple Profile in YAML Version 1.3: https://docs.oasis-open.org/tosca/TOSCA-Simple-Profile-in-YAML/v1.1/os/TOSCA-Simple-Profile-in-YAML-v1.1-os.html
- OASIS — TOSCA Specification: https://www.oasis-open.org/committees/tosca/