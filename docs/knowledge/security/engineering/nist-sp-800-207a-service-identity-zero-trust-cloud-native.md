# NIST SP 800-207A cloud-native service identity zero trust

**Issue:** A cloud-native system applies strong user authentication but trusts workload-to-workload traffic because it originates from an internal network, cluster, or namespace.
**Date:** 2026-08-12
**Author:** ORCHORDS
**Status:** documented

## Root cause

NIST SP 800-207A applies zero-trust architecture to cloud-native and multicloud applications. Network location is not sufficient trust: application and service identities need authentication and authorization at the workload interaction boundary.

**Source:** [NIST SP 800-207A](https://doi.org/10.6028/NIST.SP.800-207A).

## Fix

- give each workload a distinct, short-lived service identity; do not share long-lived client secrets across services;
- authenticate and authorize calls using workload identity, intended audience, request context, and least-privilege policy;
- place policy enforcement at appropriate application boundaries such as gateways, sidecars, or service-identity infrastructure;
- separate user identity from service identity so an authenticated user cannot become an implicit service-to-service credential;
- rotate credentials, bind policies to deployment identity, and revoke compromised workloads without broad network exceptions;
- log identity, decision, policy version, and correlation identifiers without recording secrets or sensitive payloads.

## Verification

- A workload cannot call another service solely because it is on the same network.
- A token/credential intended for service A is rejected by service B.
- Revoking a workload identity blocks new calls within the defined propagation objective.
- Policy tests cover allow, deny, cross-tenant, replay, and degraded identity-provider cases.
- Observability can explain which policy allowed or denied a request.

## Gotchas

- Service-mesh encryption alone does not prove correct application authorization.
- Avoid using mutable labels or IP addresses as the only workload identity.
- Zero trust does not remove the need for application input validation and tenant isolation.

## Related

- `security/zero-trust-architecture.md`
- `patterns/multi-tenant-data-isolation.md`
- `cloudflare/zero-trust-access.md`
