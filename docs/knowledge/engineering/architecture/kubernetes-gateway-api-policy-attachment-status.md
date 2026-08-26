# Kubernetes Gateway API policy attachment and effective status

**Issue:** A Gateway API policy object can exist without being accepted, target the wrong section, conflict with another policy, or apply differently along separate Gateway ancestry paths.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Status and decision

Gateway API describes Policy Attachment as an experimental pattern. Treat implementation-specific policies as versioned extensions and gate production use on controller conformance evidence.

Direct policies affect only the referenced object; inherited policies can affect objects through a hierarchy. Effective policy must be evaluated per target and ancestor, not inferred from object presence.

## Controls

1. Inventory installed Policy CRDs, controller/version, attachment type, supported targets, and conformance status.
2. Require direct policies to use `targetRef`, expose `status.conditions`, and report `Accepted` with reasons such as conflict or target-not-found.
3. Evaluate `sectionName` and namespace boundaries explicitly.
4. Detect multiple policies targeting the same resource and apply documented precedence/merge semantics.
5. Surface ancestor-specific status when the same backend is reached through multiple Gateways.
6. Reject unsupported policies instead of accepting and ignoring them.
7. Pin CRD/controller upgrades together and rehearse rollback.

## Verification

Create fixtures for accepted, missing-target, conflicted, wrong-section, cross-namespace, and unsupported policies. Inspect generated data-plane configuration and test actual traffic behavior; Kubernetes object status alone is insufficient.

## Gotchas

The pattern is not one universal policy API. Implementations may expose different CRDs and capabilities. Direct and inherited semantics must not be mixed. A policy attached to a Service can have distinct results for different Gateways.

## Sources

- [Gateway API: Metaresources and Policy Attachment](https://gateway-api.sigs.k8s.io/reference/policy-attachment/)
- [Gateway API GEP-713](https://gateway-api.sigs.k8s.io/geps/gep-713/)
- [Gateway API GEP-2648: Direct Policy Attachment](https://gateway-api.sigs.k8s.io/geps/gep-2648/)
