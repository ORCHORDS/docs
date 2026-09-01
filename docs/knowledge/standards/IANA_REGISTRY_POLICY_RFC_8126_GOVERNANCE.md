# IANA Registry Policy Governance with RFC 8126

## Purpose

Protocol registries make extension points discoverable and reduce collisions, but a registry is effective only when its namespace, allocation policy, review criteria, and change process match the operational risk.

This article defines a public, project-neutral method for designing and maintaining IANA registry requests using RFC 8126.

## Source status and scope

RFC 8126, **Guidelines for Writing an IANA Considerations Section in RFCs**, was published in June 2017 as Best Current Practice 26. It obsoletes RFC 5226.

RFC 8126 names registration policies ranging from Private Use and Experimental Use through First Come First Served, Expert Review, Specification Required, RFC Required, IETF Review, Standards Action, and IESG Approval. Hierarchical Allocation is also available. A registry can divide its namespace into ranges with different policies when one policy does not fit every use.

## Registry design record

Before requesting a registry, record:

- the protocol extension point and why coordinated assignment is needed;
- an unambiguous registry name and the intended IANA registry group;
- the namespace size, value syntax, valid ranges, and presentation format;
- fields stored for each registration and their validation rules;
- initial assignments, reserved values, and unassigned space;
- the registration policy for each range;
- the change controller and procedures for updates, deprecation, or correction;
- review criteria and escalation paths; and
- security and interoperability consequences of conflicting or unreviewed values.

Use explicit placeholders in drafts when IANA has not assigned values. A draft value must not be presented as an allocated code point.

## Choosing an allocation policy

Choose the least restrictive policy that still protects interoperability, security, and genuinely scarce namespace capacity.

- **Private Use** supports local coordination but does not make values globally unique.
- **Experimental Use** reserves space for experiments without implying general deployment suitability.
- **First Come First Served** offers low-friction assignment when review adds little protection.
- **Expert Review** adds judgment against documented criteria.
- **Specification Required** requires a stable, publicly available specification and expert review.
- **RFC Required**, **IETF Review**, **Standards Action**, and **IESG Approval** impose progressively specific process constraints and should be selected for a documented reason.

Excessively restrictive policy can drive implementers to deploy unregistered values, leaving the registry out of sync with reality. A policy that is too permissive can exhaust the namespace or admit conflicting semantics.

## Designated expert governance

When Expert Review or Specification Required applies:

1. Publish criteria specific enough for consistent decisions.
2. State the documentation and interoperability evidence expected from applicants.
3. Define grounds for rejection, including architectural conflict, security harm, incomplete specification, or waste of scarce values.
4. Require conflict disclosure and recusal where impartial review is not possible.
5. Preserve the request, review rationale, final recommendation, and resulting registry state.
6. Keep individual expert names out of the defining specification because appointments can change.

For IETF-created registries, the IESG appoints and can replace designated experts. The registry definition should govern the role rather than depending on a particular person.

## Change and reclamation controls

Treat changes to assigned entries as compatibility-sensitive. Before correcting, deprecating, reassigning, or reclaiming a value:

- identify deployed producers and consumers;
- determine whether the value can still appear in stored or transmitted data;
- assess whether an alias or deprecation marker is safer than reassignment;
- publish the decision and effective state; and
- retain an audit trail linking the request, approval, and registry update.

Do not assume an apparently unused assignment is safe to recycle. Implementations can persist beyond their visible registration activity.

## Verification evidence

Retain the defining specification, IANA Considerations text, namespace model, policy rationale, expert criteria, initial-value table, review correspondence, registry link, and post-publication checks. Verify that IANA’s published fields and assignments match the approved request.

Tests should cover unknown values, reserved ranges, private or experimental values, duplicate semantics, invalid syntax, and behavior when a registry entry changes status.

## Failure modes

- Selecting Standards Action by habit when a lighter policy would maintain safety.
- Using First Come First Served where expert review is needed to prevent incompatible semantics.
- Naming a policy without defining expert criteria or required registration fields.
- Treating Private Use values as globally interoperable assignments.
- Hard-coding a draft placeholder as though IANA had allocated it.
- Reclaiming a value without considering dormant deployments or stored data.
- Assuming registry publication proves that every implementation supports the registered extension.

## Sources

- RFC 8126, Guidelines for Writing an IANA Considerations Section in RFCs: https://www.rfc-editor.org/rfc/rfc8126.html
- IANA Protocol Registries: https://www.iana.org/protocols

Sources were checked on September 1, 2026.

## Scope note

This article governs registry design, allocation-policy selection, expert-review criteria, and lifecycle evidence. It does not allocate a value, replace an applicable registry’s instructions, or imply IETF endorsement of a registered extension.
