# A2A ListTasks Filtering and Visibility

## Purpose

A2A Protocol v1.0 adds a `ListTasks` operation for discovering and managing multiple tasks. Listing is not merely pagination over an internal task table: the protocol defines filters, payload controls, tenant routing, and authorization requirements that prevent callers from learning about tasks outside their access boundary.

Implementations should treat `ListTasks` as a security-sensitive query interface.

## v1.0 addition

A2A's v1.0 migration guidance identifies `ListTasks` as a new operation. Clients can filter task listings by context, state, status-update time, and pagination parameters, and can choose whether artifacts and task history are returned.

Older clients that only know `GetTask` should not assume that a server supporting v1.0 automatically exposes every task through listing.

## Request parameters

The current v1.0 specification defines `ListTasks` parameters including:

- `tenant` — optional opaque routing identifier that must match the selected `AgentInterface` when that interface declares a tenant;
- `contextId` — limits results to a conversational context;
- `status` — limits results by `TaskState`;
- `pageSize` — requested maximum number of tasks;
- `pageToken` — cursor from a previous listing response;
- `historyLength` — maximum messages to include in each returned task;
- `statusTimestampAfter` — limits results to tasks whose status timestamp is at or after the specified time; and
- `includeArtifacts` — controls whether task artifacts are included.

Clients should send only filters required for their use case rather than relying on broad listings and filtering locally.

## Page-size behavior

The v1.0 specification states that the service may return fewer tasks than the requested `pageSize`. If `pageSize` is omitted, at most 50 tasks are returned; the specified minimum is 1 and maximum is 100.

Clients must therefore:

- not assume a short page means the result set is complete;
- follow `nextPageToken` when present;
- avoid using page length as a total-count estimate; and
- tolerate server-selected page sizes within the protocol limits.

## Cursor handling

Treat `pageToken` and `nextPageToken` as opaque. Do not parse them to infer task IDs, offsets, timestamps, or database implementation details.

A client should associate a cursor with the filter set that produced it. Reusing a token after changing `contextId`, `status`, tenant, or other listing criteria can produce invalid or misleading results and should not be treated as portable behavior.

## Authorization scoping

The A2A security section requires results to be limited to the authenticated caller's authorization boundaries. `ListTasks` must return only tasks visible to that caller under the agent's authorization model.

Authorization must apply even when the request does not include a `contextId` or other narrowing filter. An empty filter set means "all tasks this caller may list," not "all tasks stored by the agent."

The protocol also requires authorization checks before database queries or operations that could leak the existence of unauthorized resources.

## Avoid existence leaks

Do not implement listing by:

1. querying all matching task rows;
2. constructing counts or cursors from that global set; and
3. removing unauthorized tasks only before serialization.

That design can leak information through counts, timing, page boundaries, or cursor behavior.

Apply the caller's access scope as part of the resource query itself whenever possible.

## Tenant boundary

When the selected `AgentInterface` declares a `tenant`, the client must carry that tenant value in requests to that interface. Treat the tenant identifier as routing context, not as proof of authorization.

A caller that knows another tenant's opaque value must not gain task visibility merely by supplying it. Authenticate and authorize independently of the routing value.

## Context filtering

`contextId` lets a client list tasks associated with a conversation or session. It should remain an opaque contextual identifier.

Do not assume every task in a context is accessible to every caller that knows the context ID. Authorization still applies to each listing request and the resulting set.

If a system supports shared conversational contexts, document how task visibility within those contexts is determined.

## Status filtering

The `status` filter selects tasks in a particular `TaskState`. Clients should use protocol-defined states rather than local status labels.

A listing result is a snapshot. A task can transition state after the response is generated, so a client should not treat membership in a `WORKING` or `INPUT_REQUIRED` page as a durable guarantee of current state.

For actions such as cancellation, fetch or operate against the task through the appropriate A2A operation and handle state changes normally.

## Status timestamp filtering

`statusTimestampAfter` is useful for incremental synchronization or dashboards. The protocol defines an ISO 8601 timestamp filter that selects tasks with status timestamps greater than or equal to the provided value.

Clients should account for:

- overlapping windows to reduce missed updates;
- duplicate tasks across successive queries;
- tasks whose timestamps are absent or behave according to server policy; and
- state changes that occur while pagination is in progress.

Use task IDs and current state to reconcile duplicates rather than assuming each incremental query produces a disjoint event stream.

## History payload control

`historyLength` controls the maximum number of messages included in each task's history. An unset value means the client does not impose a limit, while the server can apply a lower limit.

Listing many tasks with long histories can create large responses and unnecessary sensitive-data exposure. Dashboards and task pickers should usually request minimal history and fetch a specific task later when deeper detail is required.

## Artifact payload control

`includeArtifacts` defaults to false. When false, the current specification requires the `artifacts` field to be omitted entirely rather than present as `null` or an empty array.

Clients should distinguish:

- field omitted because artifacts were not requested; from
- field present as an empty array because artifacts were requested but the task has none.

This distinction matters for correct cache and UI behavior.

## REST query mapping

In the HTTP+JSON binding, `ListTasks` maps to `GET /tasks`. Query parameters use camelCase, for example:

- `contextId`;
- `pageSize`;
- `pageToken`; and
- other defined request fields.

Query values must be URL-encoded. Custom bindings should preserve the same functional semantics even when the transport representation differs.

## Client reconciliation pattern

A resilient client can:

1. choose the narrowest useful filters;
2. request a bounded page size;
3. store the filter set alongside the cursor;
4. process tasks by opaque `id`;
5. follow `nextPageToken` until absent;
6. tolerate duplicates or state changes between pages;
7. fetch individual tasks when fresh detail is required; and
8. discard cursors when the listing criteria or authorization context changes.

## Server implementation checklist

Verify that the server:

- authenticates the caller before listing;
- applies authorization scope before resource lookup;
- enforces tenant routing without treating tenant as authentication;
- supports the protocol filter semantics;
- enforces page-size limits;
- generates opaque pagination tokens;
- omits artifacts when `includeArtifacts` is false;
- respects requested history bounds;
- does not leak unauthorized task counts or existence; and
- produces equivalent behavior across supported protocol bindings.

## Sources

- A2A Protocol v1.0 — Specification, List Tasks: https://a2a-protocol.org/latest/specification/
- A2A Protocol — What's New in v1.0: https://a2a-protocol.org/latest/whats-new-v1/
- A2A Protocol v1.0 — Security Considerations, Data Access and Authorization Scoping: https://a2a-protocol.org/latest/specification/#security-considerations

## Scope note

This article describes protocol-level `ListTasks` behavior and implementation safeguards. Agent-specific authorization models, retention rules, and task-discovery policies remain application decisions.