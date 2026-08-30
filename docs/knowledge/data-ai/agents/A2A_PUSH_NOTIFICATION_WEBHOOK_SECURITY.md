# A2A Push Notification Webhook Security

## Purpose

A2A v1.0 supports asynchronous task updates through push notifications. Because the agent sends callbacks to a client-supplied webhook, the callback path is also a security boundary.

## Controls

1. Require HTTPS for production webhook endpoints.
2. Authenticate every callback and verify the notification belongs to an expected task.
3. Validate destination URLs before delivery; reject localhost, link-local, and private-address targets unless an explicitly controlled deployment requires them.
4. Treat callback credentials as secrets, use narrow-purpose credentials, and rotate them according to the application's secret-management policy.
5. Make receivers idempotent because duplicate delivery may occur.
6. Apply rate limits and bounded retry/backoff so a failing or malicious endpoint cannot create unbounded work.
7. Avoid returning secrets when push-notification configurations are queried.

## Source

- A2A Protocol v1.0 specification, Push Notification Security: https://a2a-protocol.org/dev/specification/

## Scope note

These controls address protocol-facing webhook risks. Network egress policy, DNS rebinding defenses, proxy behavior, and cloud-metadata protection still require deployment-specific controls.
