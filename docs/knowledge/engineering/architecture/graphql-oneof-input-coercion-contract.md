# GraphQL OneOf Input Coercion Contract

**Issue:** An input object that models mutually exclusive choices with nullable fields accepts ambiguous requests unless exclusivity is enforced during GraphQL coercion.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls
- Declare mutually exclusive input objects as OneOf input objects using the schema form supported by the September 2025 GraphQL specification.
- Define every member as nullable and without a default value. The OneOf rule operates on which member is provided, not on default substitution.
- Require exactly one member to be supplied and require that member's coerced value to be non-null.
- When a variable supplies the selected member, declare the variable as non-null so null cannot bypass the OneOf contract.
- Expose and test `__Type.isOneOf` in schema tooling; reject deployments where gateways, code generators, or validators silently drop the contract.
- Still validate the selected member's domain rules in the resolver and keep authorization independent of input coercion.

## Verification
- Contract-test zero members, two members, one null member, and a nullable variable; all are rejected before resolver side effects.
- Test every valid single-member branch and confirm generated clients preserve the OneOf metadata.
- Compare gateway and origin behavior so federated or persisted-query paths enforce identical coercion.

## Gotchas
GraphQL's output union and input OneOf are different mechanisms. A name containing `oneOf` does not enforce anything without schema support.

## Official sources
- https://spec.graphql.org/September2025/
