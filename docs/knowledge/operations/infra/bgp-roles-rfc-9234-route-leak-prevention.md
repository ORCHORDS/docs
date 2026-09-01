# BGP Roles and RFC 9234 Route-Leak Prevention

**Issue:** Import and export policy relies on local naming conventions and manual peer classification, so a relationship mismatch or policy error can propagate routes beyond their intended scope.

**Date:** 2026-09-01
**Author:** ORCHORDS
**Status:** documented

## Standards context

RFC 9234, published in May 2022, is an IETF Standards Track RFC for route-leak prevention and detection using roles in BGP OPEN and UPDATE messages. It defines the BGP Role Capability and the transitive Only-To-Customer (OTC) path attribute.

The RFC complements, rather than replaces, ordinary prefix filters, route-policy review, RPKI origin validation, maximum-prefix limits, and monitoring. It addresses relationship-based propagation; it does not prove that a route is authorized, reachable, or safe.

## Relationship model

RFC 9234 defines Provider, Customer, Peer, Route Server, and Route Server Client roles. Valid role pairings express the relationship from each neighbor's perspective. Configure roles from contracts and routing intent, not from traffic direction or an inferred Autonomous System size.

Maintain a peer register containing:

- local and remote Autonomous System numbers;
- session endpoints and address families;
- local role and expected remote role;
- commercial or organizational relationship owner;
- accepted and advertised prefix scope;
- role-capability and OTC support;
- import, export, RPKI, community, and maximum-prefix policies;
- route-server behavior where applicable; and
- exception, maintenance, and rollback contacts.

A single session is a poor fit for a relationship that changes per prefix. Where practical, use separate sessions or explicitly designed policy rather than forcing mixed semantics into one role.

## OPEN capability negotiation

The BGP Role Capability is exchanged during session establishment. Compatible role pairs provide an early check that both sides configured the relationship consistently. Decide whether role negotiation is required per peer and document behavior when the neighbor does not advertise the capability.

RFC 9234 supports incremental deployment. Enabling strict rejection everywhere without confirming peer support can cause avoidable outages. Use staged rollout:

1. inventory implementation support;
2. configure expected roles without strict enforcement where appropriate;
3. observe capability exchange and mismatches;
4. resolve contractual or configuration discrepancies;
5. enable stricter behavior only for approved peer groups; and
6. preserve an emergency rollback that does not remove ordinary route filters.

A session that successfully negotiates roles is not evidence that import and export policy is otherwise correct.

## OTC handling

OTC marks routing information learned from upstream, lateral, or route-server relationships so it is not propagated contrary to the customer-provider model. Its transitive behavior supports leak detection and prevention across capable and partially capable paths.

Implement OTC handling according to the local role, peer relationship, and RFC rules. Do not improvise attribute insertion or stripping from a simplified slogan. Validate the router's actual behavior for each role and address family in a lab before production rollout.

Treat unexpected OTC presence, absence, or Autonomous System value as a routing-security signal. Response should distinguish a local policy defect, remote misconfiguration, unsupported legacy hop, route-server behavior, and a genuine leak.

## Defense in depth

RFC 9234 controls should operate with:

- explicit inbound and outbound prefix filters;
- customer prefix and Autonomous System authorization records;
- RPKI Route Origin Validation policy;
- Internet Routing Registry or equivalent policy data where appropriate;
- maximum-prefix and rate controls;
- bogon and special-use filtering;
- community governance;
- route-policy peer review and staged deployment; and
- control-plane telemetry and external route observation.

RPKI origin validation does not prevent every route leak because a leaked route can retain a valid origin. Conversely, OTC does not establish origin authorization.

## Change workflow

1. Open a change record linked to the peer register and relationship evidence.
2. Capture current OPEN capabilities, route counts, selected paths, advertisements, and policy checksums.
3. Test compatible and incompatible role pairs, missing capability, expected OTC propagation, and prohibited propagation.
4. Deploy to a low-risk session or maintenance group first.
5. Monitor session resets, rejected updates, route-count deltas, path changes, and traffic shifts.
6. Stop or roll back on unexplained reachability loss or policy divergence.
7. Retain before-and-after configurations, commands, observations, and approval.

Never paste authentication material, private topology, or customer routing details into public evidence.

## Incident response

For a suspected leak, preserve relevant UPDATEs, path attributes, peer role, timestamps, configuration versions, and external observations. Apply the smallest safe containment through import/export filters or session control. Coordinate with the neighbor and affected networks using approved contacts.

After containment, determine why preventive policy, role negotiation, OTC handling, or monitoring did not stop the event. Update the peer register and regression tests before restoring normal propagation.

## Verification

- Establish every valid role pair in a controlled environment and confirm capability behavior.
- Present incompatible role pairs and confirm the configured strict or non-strict response.
- Advertise representative customer, provider, peer, and route-server paths and inspect OTC behavior hop by hop.
- Test a valid-origin route leak to confirm defense does not rely only on RPKI.
- Test a non-supporting peer and verify incremental-deployment policy.
- Compare router configuration to the contractual peer register and external route collectors.
- Exercise rollback without removing prefix filters or maximum-prefix protections.

## Failure modes

- Inferring roles from observed traffic rather than the routing relationship can invert policy.
- Enabling strict role negotiation before checking peer support can drop legitimate sessions.
- Treating OTC as a replacement for prefix filtering and RPKI removes defense in depth.
- Stripping an unknown transitive attribute without understanding the implementation can defeat propagation signaling.
- Using one role for mixed per-prefix relationships creates ambiguous enforcement.
- Declaring success because the BGP session is established ignores route-policy correctness.
- Logging private peer details or authentication material in broad evidence creates a separate security exposure.

## Official sources

- [RFC 9234: Route Leak Prevention and Detection Using Roles](https://www.rfc-editor.org/rfc/rfc9234.html)
- [RFC 7908: Problem Definition and Classification of BGP Route Leaks](https://www.rfc-editor.org/rfc/rfc7908.html)

Source status was checked on September 1, 2026.

## Scope note

This article provides operational governance, not vendor-specific commands or a complete routing-security architecture. Validate behavior against current router documentation, peer agreements, network design, and applicable incident procedures.
