# OASIS XACML 3.0 Authorization Template Governance

## Purpose

OASIS XACML (eXtensible Access Control Markup Language) 3.0 defines a declarative authorization language for expressing access control policies. XACML 3.0 extends XACML 2.0 with administrative delegation, obligations, advice, and the new JSON profile (XACML JSON) alongside the XML profile. XACML separates the policy decision point (PDP), the policy enforcement point (PEP), the policy administration point (PAP), and the policy information point (PIP). This article governs the application of XACML 3.0 as a template for designing and managing authorization policies.

## Scope

The specification applies to any organization that uses XACML to express access control policies. Within this knowledge base, the article covers the XACML policy structure (PolicySet, Policy, Rule, Target, Condition, Obligation, Advice), the reference architecture (PDP, PEP, PAP, PIP), the JSON profile, and the documentation of the policy set. It does not cover the substantive access control model used in any specific deployment; readers should consult the appropriate resources for that.

## Workflow

1. Identify the resources to be protected, the subjects requesting access, the actions to be controlled, and the environment attributes relevant to the decisions.
3. Express the access control policies in XACML: PolicySet and Policy containing Rules, with Targets that match subjects, resources, actions, and environment.
4. Use Conditions for fine-grained decisions (e.g., "subject.role == 'manager' AND resource.owner == subject.id").
5. Define Obligations (mandatory actions to be performed) and Advice (optional recommendations) for the policy's enforcement context.
6. Compose multiple PolicySets into a hierarchy. XACML supports administrative delegation: a parent PolicySet can delegate authority to a child PolicySet, with constraints on the delegation.
7. Deploy the XACML infrastructure: PEP at the access point, PDP evaluating the policy, PAP managing the policies, PIP providing attributes.
8. Use either the XML or JSON profile of XACML 3.0 as appropriate to the deployment.

## Controls and evidence

Authorization evidence includes the XACML policy set (the documents), the deployment architecture, the access decisions and the policies that produced them, the obligations enforced, and the audit logs. Each policy should be documented with its purpose, its author, its version, and its effective date.

## Validation

Validation should confirm the policies are syntactically valid XACML, the reference architecture is in place, the PEP enforces the PDP's decisions, obligations are enforced at the PEP, and policies are reviewed for redundancy, conflict, and unintended access. Conflict and redundancy analysis should be performed when policies change.

## Failure correction

Common failure modes: policies are scattered across multiple documents and conflict (corrective: consolidate into a single hierarchy and review for conflicts); obligations are specified but not enforced at the PEP (corrective: enforce obligations at the PEP and test); PIP attributes are stale or unavailable (corrective: monitor the PIP and define fallbacks); administrative delegation is used without constraints (corrective: define the constraints on delegation and document them).

## Limitations

XACML is a policy language; it does not certify any deployment. The standard does not address the authentication identity or attribute source; those are governed by other standards and services. XACML's complexity has been a barrier to adoption; many deployments use simpler policy languages (OPA/Rego, Cedar) and reserve XACML for inter-vendor interoperability.

## Scope note

This article summarizes project-neutral use of OASIS XACML 3.0 as a template. It does not assert any specific authorization deployment's conformance or claim any certification outcome.

## Canonical sources

- OASIS XACML 3.0 — eXtensible Access Control Markup Language (XACML) Version 3.0: https://docs.oasis-open.org/xacml/3.0/xacml-3.0-core-spec-os.pdf
- OASIS XACML 3.0 JSON Profile — JSON Profile of XACML 3.0: https://docs.oasis-open.org/xacml/xacml-json/v1.1/cs02/xacml-json-profile-v1.1-cs02.pdf