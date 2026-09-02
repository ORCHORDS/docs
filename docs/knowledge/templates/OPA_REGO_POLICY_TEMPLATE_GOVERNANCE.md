# OPA Rego Policy Template Governance

## Purpose

Open Policy Agent (OPA, CNCF Graduated) evaluates policies expressed in the Rego language against structured data (typically JSON) and returns allow/deny decisions or arbitrary structured output. A reusable OPA Rego policy template captures the package declaration, import statements, default decision, input schema reference, helper rules, and the primary allow/deny rule skeleton so that policy authors can specialize only the differentiating decision logic. Without a template, policies drift in style, package naming, and rule placement, which complicates code review and bundle packaging.

The template must remain generic: it MUST NOT embed real input payloads, role names, or organization identifiers that identify specific systems or customers.

## Scope

This template applies to OPA Rego policies run via the `opa eval`, `opa test`, or `opa run` commands, or invoked through the OPA-as-a-service Daemon (OAD) protocol. It does not address the Stylus extension language (deprecated in OPA 1.0) or EGo-compiled policies, which require separate templates. It does not address OPA's WASM bundle format except by reference; bundle construction is governed by a separate template. The template does not cover authorization frameworks built on top of OPA such as OPAL (Open Policy Administration Layer) or KubeArmor; those frameworks have their own templates.

## Workflow

1. Open the template and complete the header with the policy package identifier, the policy version, the policy owner, the date, and the input schema reference.
2. Declare the package using the team's standard naming convention (for example `org.policy.service.action`).
3. Import required built-in packages: `future.keywords`, `data`, `input`.
4. Declare input-schema-based type-checking at the top of the policy using `if` guards with type assertions or a generated schema.
5. Define helper rules for repeated logic (for example `_is_owner(user) if ...`).
6. Define the primary allow/deny rule with explicit default: `default allow := false` followed by `allow if { ... }`.
7. Add per-package test rules in `_test.rego` files that pair `allow`, `deny`, and edge cases.
8. Validate the policy locally with `opa fmt --diff`, `opa check`, and `opa test ./...`.
9. Package the policy into a bundle with `opa build` and push to the policy distribution point.
10. Record the policy in the policy catalog with version, signature, and last-evaluated timestamp.

## Controls and evidence

- Header records package, owner, version, date, and schema reference.
- `default` declaration is present at the top of the policy file.
- Helper rules are clearly marked (leading underscore convention).
- Test file enumerates allow and deny cases plus at least one edge case.
- Bundle manifest records policy version and SHA-256.
- Policy catalog entry includes signature verification status.

## Validation

- `opa fmt --diff` produces no output (clean format).
- `opa check` exits 0.
- `opa test` shows 100% pass rate on the package.
- Bundle generation succeeds with a deterministic SHA-256.
- The policy is signature-verified by the consuming service (for example Gatekeeper for Kubernetes admission control).
- Evaluation latency measured against the production input volume is within the SLO.

## Failure correction

Common defects include omitting the `default` declaration (which can yield undefined behavior), placing helper rules without the underscore convention, and missing test coverage for negative cases. Corrective actions include adding explicit defaults, normalizing helper naming, and requiring test coverage for both allow and deny cases in CI.

## Limitations

- The template does not address bundle construction or distribution; that is governed by a separate template.
- It does not cover WASM compilation and signing; a separate template is required.
- It does not substitute for input-schema governance; the schema source must be agreed upstream.
- It does not address policy versioning or rollback semantics; those are governed by the policy distribution platform.

## Scope note

This template is part of the **templates** leaf. Sibling leaves cover: **platforms** (OPA deployment and bundle distribution), **engineering** (policy testing in CI), **security** (decision logging and audit), and **operations** (policy catalog maintenance). The template should be used together with those sibling-leaf articles.

## Canonical sources

- Open Policy Agent documentation (CNCF Graduated): https://www.openpolicyagent.org/docs
- OPA Rego language reference: https://www.openpolicyagent.org/docs/latest/policy-language/
- OPA GitHub repository (CNCF Graduated): https://github.com/open-policy-agent/opa

Sources were verified on September 1, 2026.
