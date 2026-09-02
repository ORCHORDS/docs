# OASIS TOSCA SOLPolicy Modeling Governance

## Purpose

OASIS TOSCA SOLPolicy (Structured Object Language for Policy) extends TOSCA with a structured approach to expressing policies for cloud applications. SOLPolicy provides a typed policy framework with policy types (placement, scaling, security, monitoring), policy triggers, and policy conditions that drive automated decisions within the TOSCA orchestration framework. This article governs the application of SOLPolicy as a template for expressing cloud application policies in TOSCA templates.

## Scope

The specification applies to TOSCA templates that need to express policies. Within this knowledge base, the article covers the SOLPolicy structure (policy types, policy triggers, policy conditions, policy actions), the integration with TOSCA node templates and groups, and the documentation of policies. It does not cover the broader TOSCA orchestration framework; readers should consult the TOSCA specification for that.

## Workflow

1. Identify the policies the cloud application needs: placement constraints, scaling rules, security requirements, monitoring expectations, update policies.
2. Define or reuse policy types in TOSCA. Each policy type has triggers (when the policy is evaluated), conditions (when the policy applies), and actions (what the policy does).
3. Apply policies in the TOSCA template:
   - To node templates: each node can have one or more policies attached.
   - To groups: groups of nodes can share policies, allowing the policy to be defined once and applied to multiple nodes.
4. Express the conditions using structured or constraints:
   - Equal, not equal, greater than, less than, in range.
   - Boolean combinations of conditions.
   - Time-based or event-based triggers.
5. Express the actions:
   - Placement actions: select a host or region.
   - Scaling actions: scale in or scale out based on conditions.
   - Security actions: enforce authentication, authorization, or encryption.
   - Monitoring actions: configure thresholds, alerting, or notification.
6. Validate the policy against the SOLPolicy specification and test the policy in the orchestrator.

## Controls and evidence

Policy evidence includes the policy type definitions, the policy attachments, the validation results, and the runtime behavior records. Each policy should be reviewable against its purpose and its expected behavior.

## Validation

Validation should confirm the policies are syntactically valid SOLPolicy, the conditions correctly capture the intent, the actions correctly implement the intent, and the runtime behavior matches the expected behavior. Sample-based testing across policies confirms the design.

## Failure correction

Common failure modes: policies are not reusable (correct: define policy types and apply via groups); conditions are not specific enough to drive deterministic actions (correct: specify the conditions with structured or constraints); actions are not tested in the orchestrator (correct: deploy and test before production); policy changes are not versioned (correct: version the policy definitions alongside the template).

## Limitations

SOLPolicy is a structured language; it does not certify any policy or any deployment. The specification depends on the orchestrator's implementation of the policy actions; different orchestrators may support different action types. Complex policies may require additional tooling beyond what SOLPolicy expresses.

## Scope note

This article summarizes project-neutral platform use of OASIS TOSCA SOLPolicy. It does not assert any specific template's conformance or claim any certification outcome.

## Canonical sources

- OASIS — TOSCA SOLPolicy (Structured Object Language for Policy): https://docs.oasis-open.org/tosca/tosca-solpolicy/v1.0/csd01/tosca-solpolicy-v1.0-csd01.html
- OASIS — TOSCA Specification: https://www.oasis-open.org/committees/tosca/