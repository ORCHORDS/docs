# A2A Push Notification Configuration Lifecycle

## Purpose

A2A v1.0 supports more than the secure delivery of webhook callbacks. It also defines a lifecycle for creating, retrieving, listing, and deleting task-scoped push-notification configurations.

This lifecycle should be governed separately from webhook transport security. A secure callback endpoint can still be exposed or mismanaged if configuration records are not properly scoped and authorized.

## Current v1.0 operations

A2A v1.0 renamed the earlier push-notification operations to resource-oriented methods:

- `CreateTaskPushNotificationConfig`
- `GetTaskPushNotificationConfig`
- `ListTaskPushNotificationConfigs`
- `DeleteTaskPushNotificationConfig`

The server advertises support through `capabilities.pushNotifications: true` in its Agent Card. A configuration can be supplied with the initial message operation or created separately for an existing task.

## Lifecycle guidance

1. Verify that the server advertises push-notification support before attempting configuration operations.
2. Authorize access to the parent task before creating, reading, listing, or deleting a configuration.
3. Treat the configuration ID as a task-scoped resource identifier; do not use it as proof of authorization.
4. Support multiple configurations per task without allowing one caller to enumerate another caller's webhook URLs, tokens, or authentication material.
5. Paginate configuration listings using the protocol's `pageSize`, `pageToken`, and `nextPageToken` semantics rather than inventing an incompatible cursor contract.
6. Redact secret-bearing fields from logs, diagnostics, audit views, and user-facing error messages.
7. Make deletion idempotent at the application boundary where practical, but do not claim that deleting a configuration recalls notifications that were already sent or queued outside the configuration store.
8. Revalidate task access on each management operation instead of assuming that permission at creation time remains valid indefinitely.
9. Keep tenant routing consistent with the selected Agent Interface when multi-tenancy is in use.

## Distinguish configuration from delivery

Configuration management answers **where and how future notifications should be sent**. Delivery security answers **whether an actual callback is safe, authenticated, relevant, and resistant to abuse**. Implementations need both controls.

For callback-specific controls such as HTTPS validation, SSRF defenses, receiver authentication, idempotency, and retry limits, see [A2A Push Notification Webhook Security](A2A_PUSH_NOTIFICATION_WEBHOOK_SECURITY.md).

## Version note

A2A v1.0 renamed the v0.3 push-notification operations and flattened the configuration model. Implementations supporting older revisions should negotiate the protocol version instead of silently mapping old method names onto v1.0 behavior.

## Sources

- A2A Protocol — Streaming & Asynchronous Operations: https://a2a-protocol.org/latest/topics/streaming-and-async/
- A2A Protocol — Protocol Definition: https://a2a-protocol.org/latest/definitions/
- A2A Protocol — What's New in v1.0: https://a2a-protocol.org/latest/whats-new-v1/

## Scope note

This article covers protocol configuration lifecycle and authorization boundaries. It does not define implementation-specific storage schemas, retention periods, webhook retry queues, or credential-rotation schedules.