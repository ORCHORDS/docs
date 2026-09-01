# Agent Policy Decisions with OpenID AuthZEN

## Purpose

Agent systems often place policy enforcement in gateways, tool adapters, and workflow services while centralizing policy decisions in a policy decision point. The OpenID AuthZEN Authorization API defines a common request and response model for asking whether a subject may perform an action on a resource in a context. It can reduce proprietary coupling between an agent's policy enforcement point and an authorization service, but it does not define the policy language, identity proofing, or enforcement logic.

The basic decision request contains `subject`, `action`, `resource`, and `context` properties. Each entity has a `type`, an `id`, and optional properties. The decision response communicates whether access is allowed. Implementations should bind those abstract entities to locally governed identity and resource models instead of sending arbitrary model-generated labels.

## Implementation workflow

1. Inventory each privileged agent operation and locate its policy enforcement point. The component able to prevent the operation—not the language model—must enforce the result.
2. Define stable mappings from authenticated principals to AuthZEN subjects, registered tool operations to actions, and concrete targets to resources. Document required context such as tenant, assurance level, delegation chain, or request time.
3. Build the authorization request from trusted runtime state. A model may propose an operation, but it must not supply authoritative subject identity, tenant, resource owner, or authentication strength.
4. Authenticate the enforcement point to the policy decision point and protect requests in transit. Apply network and service authorization so unrelated workloads cannot query or influence decisions.
5. Validate the response, enforce `false` as denial, and perform the operation only after an affirmative decision that is still applicable to the exact target and action.
6. Record a correlation identifier, policy decision, policy version or deployment identifier when available, and enforcement outcome. Avoid logging confidential context fields unnecessarily.

Use the evaluation endpoint for one decision and the evaluations endpoint only when the implementation supports the required multi-decision semantics. Batch optimization must not blur which subject-action-resource tuple each result covers.

## Controls

Adopt deny-by-default behavior for malformed requests, unavailable policy services, unknown entity types, missing mandatory context, and invalid responses. Keep entity property allowlists. Free-form model output must not become policy context because it can introduce attacker-controlled claims that policy authors mistake for trusted facts.

Bind decisions to canonical identifiers. Resolve aliases before authorization and before execution so a permitted resource cannot be swapped for another through redirects, symbolic links, mutable names, or tenant-relative identifiers. If the tool performs several effects, either authorize each effect or define a reviewed compound action whose scope is explicit.

Decision caching needs a documented key and lifetime. Include every input that can affect policy, including tenant and relevant environmental context. Never reuse a decision across subjects or resources. Invalidate or sharply limit caches where revocation, membership changes, or risk posture must take effect quickly. AuthZEN interoperability does not make a stale authorization safe.

## Validation and evidence

Create a policy test matrix covering allowed, denied, malformed, cross-tenant, unknown-action, expired-session, and altered-resource cases. Confirm that the enforcement point sends canonical IDs and that changing any security-relevant tuple field triggers a separate decision. Include tests where model-provided context conflicts with authenticated runtime context; trusted context must win or the request must be rejected.

Run contract tests against the policy service for request schema, response parsing, transport errors, and version compatibility. Store policy source revisions, deployment records, test results, sampled decision logs, and enforcement logs as evidence. Correlation should show that an allowed decision preceded the corresponding operation and covered the same normalized resource.

## Failure handling

When the policy decision point times out or returns an invalid response, stop the privileged operation and return a bounded authorization-unavailable error. Do not convert operational failure into permission. Retries should be limited, deadline-aware, and safe from multiplying the underlying side effect, which must not begin before authorization completes.

If authorization succeeds but execution discovers a materially different resource or action, discard the decision and reauthorize. If audit reconciliation finds an operation without a matching decision, treat it as a security incident: disable the affected path if necessary, preserve logs, determine whether enforcement was bypassed, and test the repair. A protocol-compatible response is not evidence that local policy was correct; policy review remains a separate control.

## Canonical sources

- OpenID Foundation, *AuthZEN Authorization API 1.0*: https://openid.net/specs/authorization-api-1_0.html
- OpenID Foundation AuthZEN Working Group: https://openid.net/wg/authzen/
- IETF, *OAuth 2.0 Rich Authorization Requests* (RFC 9396), useful for distinguishing requested authorization details from a policy decision API: https://www.rfc-editor.org/rfc/rfc9396
