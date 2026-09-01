# Delegated Authority Evidence Chain Under OpenID AuthZEN

## Scope

Agents act on behalf of users and systems. The act of delegation - who authorized what, for which resource, under which policy - is the part that most often goes unrecorded in agent systems. An agent that calls a downstream API may carry a token issued to a human, or a token issued to the agent itself, or a token issued by the agent on the basis of a prior delegation. The downstream system needs evidence of the chain by which the authority reached the call, and the operator needs evidence that the chain was honored.

The OpenID AuthZEN Authorization API 1.0 defines a model in which authorization decisions return structured evidence alongside the verdict. This article applies the AuthZEN evidence model to agent delegation, treating the evidence chain as a first-class object that travels with the call and that is verifiable by downstream systems.

## Workflow or implementation guidance

1. Model delegation as a chain rather than as a single grant. A user delegates to an agent, the agent delegates to a sub-task, the sub-task invokes a tool. Each link is a delegation with its own evidence, and the chain is the concatenation of the links, not the replacement of them.
2. Adopt the AuthZEN request shape: subject, action, resource, and optional context. For each link in the delegation chain, record the subject that exercised authority, the action that was authorized, the resource that was targeted, and the contextual facts that informed the decision. The shape is the contract that makes evidence comparable.
3. Carry evidence with the call. When the agent invokes a downstream tool, the call should include the evidence chain in a form the downstream system can verify: who delegated, what policy applied, when the delegation was issued, and any constraints that bound it. Carrying the evidence is what makes the chain inspectable.
4. Treat the decision point as the boundary of evidence. Each link in the chain is the output of an authorization decision at a defined boundary; the boundary emits evidence about its inputs and outputs. Evidence without a defined boundary is not chain-of-delegation evidence; it is a log line.
5. Define what evidence is sufficient for each downstream call. A read-only call may require evidence of identity and scope. A destructive call may require evidence of identity, scope, policy, and human confirmation. The chain's sufficiency is a function of the call's risk, not a constant.
6. Issue evidence with cryptographic integrity where the downstream system requires verifiable evidence. AuthZEN evidence can be augmented with signatures or verifiable credentials when the downstream system is not directly trusting the issuing authority. Without integrity, evidence is assertion.
7. Propagate evidence across tool boundaries. When the agent invokes a tool, the tool's downstream invocation should also carry the chain. Where the tool does not natively support evidence propagation, the agent should wrap the call with evidence at the next boundary the operator controls.
8. Make evidence retention policy explicit. The chain is evidence only if it is retained; transient evidence does not support after-action review. Define retention by chain element and link the chain to the audit log of the run.

## Controls

Policy versioning matters. Evidence produced under one version of a policy cannot be safely interpreted under another; treat policy versions as part of the evidence record and refuse to interpret evidence under a policy version that no longer applies to the resource or subject. A chain that survives across policy changes must do so through explicit bridging rules.

Subject identity in the chain must be unambiguous. Where the chain includes tokens, identifiers, and aliases, define canonicalization so a downstream system can verify identity without resolving ambiguity. Evidence that depends on resolving identity at the wrong time becomes unverifiable at the right time.

Decision caching must respect evidence currency. A cached decision may be reused only when the evidence chain that produced it is still valid for the resource and subject under current policy. Without that check, a cached decision becomes a long-lived privilege grant by accident.

## Validation evidence

Demonstrate the chain on a representative flow. A user delegates to an agent, the agent delegates to a sub-task, the sub-task invokes a destructive tool. Each link produces AuthZEN-shaped evidence with subject, action, resource, context, and decision. The downstream tool receives the chain, verifies it, and records the verification.

Demonstrate negative cases. A chain with a missing link is rejected at the downstream boundary with a stable error. A chain with a link from a policy version that no longer applies is rejected. A chain whose evidence has been tampered with is rejected when the downstream system verifies integrity.

Demonstrate operational evidence. Decisions are logged with their evidence chains. Reviews can reconstruct a decision at any link. Policy changes produce evidence migration events that show which chains were bridged to the new policy and which were allowed to expire.

## Failure modes and correction

The dominant failure is evidence without chain semantics. The agent logs authorization decisions but does not model them as links, and the chain is reconstructable only by inference. Correct by enforcing the chain model at the agent runtime and by validating that emitted evidence satisfies chain requirements.

A second failure is evidence exposed in the wrong places. Sensitive attributes appear in evidence carried to systems that should not see them. Correct by classifying evidence attributes per downstream system and redaction-mapping at the boundary, with the same discipline applied to the chain.

A subtler failure is policy drift across delegation. A policy updated for one link is not propagated to others, and the chain includes both pre-update and post-update evidence. Correct by treating policy updates as version events that either bridge or invalidate evidence under explicit rules.

## Limitations

AuthZEN evidence assumes the issuing authority is trusted by the verifier; cryptographic integrity does not establish trust in the issuer. The model also assumes evidence is structured and machine-readable, which adds integration cost when downstream systems are legacy or human-mediated. Delegation depth has practical limits because each link adds evidence size and verification cost. The chain is also only as strong as the weakest link, and one link's evidence being weak is enough to weaken the chain.

## Canonical sources

- **OpenID, AuthZEN Authorization API 1.0 (Final Specification):** https://openid.net/specs/authorization-api-1_0.html
- **OpenID, AuthZEN Working Group specifications index:** https://openid.net/wg/authzen/specifications/
- **OpenID, AuthZEN editors' draft and reference implementation:** https://openid.github.io/authzen/
