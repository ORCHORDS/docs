# A2A Authorization Before Resource Lookup

## Purpose

A2A v1.0 requires authorization boundaries to be enforced before operations that could reveal resources outside the caller's scope. This prevents task and configuration APIs from becoming resource-enumeration channels.

## Controls

1. Authenticate the caller before task-resource access.
2. Resolve tenant, project, workspace, or other authorization scope before querying for protected task data.
3. Perform authorization checks before database queries or operations that could disclose whether an out-of-scope resource exists.
4. Apply the same scope rules to task listing, task retrieval, cancellation, subscriptions, and push-notification configuration operations.
5. Keep error behavior consistent enough that unauthorized callers cannot infer protected resource existence from timing or response differences.
6. Test cross-tenant and cross-project identifiers as negative authorization cases.

## Source

- A2A Protocol v1.0 specification, authorization requirements: https://a2a-protocol.org/dev/specification/

## Scope note

A2A does not prescribe an application's role or tenant model. Implementations remain responsible for defining and testing their authorization policy.
