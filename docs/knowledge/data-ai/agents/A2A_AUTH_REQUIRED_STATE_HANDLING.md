# A2A AUTH_REQUIRED State Handling

## Purpose

A2A v1.0 defines `TASK_STATE_AUTH_REQUIRED` as an interrupted task state indicating that additional authorization is required before processing can continue. The state is a coordination signal; it is not itself proof that any operation has been authorized.

## Core security rule

Implementations must not treat the transition to `TASK_STATE_AUTH_REQUIRED` as a credential or permission grant. The scope, validity, representation, and revocation semantics of the authorization decision or credential are defined outside the core state value by the implementation, credential issuer, or an agreed A2A extension.

## Agent responsibilities

When an agent needs the client to help fulfill an authorization requirement:

1. Track the operation as a `Task`.
2. Transition the task to `TASK_STATE_AUTH_REQUIRED`.
3. Include a status message that explains what authorization is needed unless the details were already negotiated through another mechanism.
4. Arrange a defined channel for receiving the resulting credential or authorization decision.
5. Re-check authorization for the specific protected operation before resuming it.
6. Avoid assuming that a credential obtained for one operation automatically authorizes later messages or unrelated actions.

A task in `AUTH_REQUIRED` is interrupted rather than terminal. Depending on the authorization model, an implementation may pause execution and resume after a client response or may wait for an out-of-band authorization provider.

## Client responsibilities

A client that receives an `AUTH_REQUIRED` task should decide how the authorization request will be resolved. It may:

- send a message to the task to negotiate, correct, or reject the request;
- contact a person, service, or another agent that can authorize the operation; or
- fulfill the request through an out-of-band or extension-negotiated mechanism.

If the client is itself acting as an A2A agent, it may propagate the need for authorization through its own task lifecycle rather than silently granting authority on behalf of its upstream user.

## Stream and lifecycle behavior

Blocking send operations wait until a task reaches either a terminal state or an interrupted state such as `INPUT_REQUIRED` or `AUTH_REQUIRED`. Clients should therefore treat an `AUTH_REQUIRED` response as an expected pause in the workflow and not as successful completion.

Task status transitions and any credential-handling channel should be logged carefully without placing raw secrets into status messages, metadata, or ordinary task history unless an explicitly designed secure extension requires it.

## Sources

- A2A Protocol v1.0 — Protocol specification and `TASK_STATE_AUTH_REQUIRED` semantics: https://a2a-protocol.org/latest/specification/
- A2A Protocol — Protocol definitions: https://a2a-protocol.org/latest/definitions/

## Scope note

A2A coordinates the need for authorization but does not define the authorization credential's full security model. Authentication, consent, credential transport, scope, revocation, and protected-operation checks remain implementation- or extension-specific.