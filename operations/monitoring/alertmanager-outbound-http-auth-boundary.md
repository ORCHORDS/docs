# Alertmanager outbound HTTP authentication boundary

**Problem**

Webhook and API receivers share HTTP client configuration that can expose credentials or weaken TLS if copied broadly.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use for authenticated outbound receivers with an explicit endpoint trust policy.

## Controls

- Prefer scoped OAuth2 or authorization files over inline secrets.
- Pin TLS roots/server names and restrict redirects/proxies.
- Use separate credentials per receiver trust domain.

## Implementation

- Reference secret files with protected permissions.
- Keep tokens out of rendered config and logs.
- Rotate through reload with rollback.

## Tests

- Test expiry, wrong audience, TLS mismatch, redirect, proxy, file permission, reload, and receiver timeout.

## Gotchas

- OAuth token requests are separate outbound traffic.
- Redirects can cross origins.
- Config validation does not prove endpoint identity.

## Official sources

- [Official documentation](https://prometheus.io/docs/alerting/latest/configuration/#http_config)
