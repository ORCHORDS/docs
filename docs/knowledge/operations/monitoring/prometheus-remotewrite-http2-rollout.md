# Prometheus remote-write HTTP/2 rollout

**Problem**

HTTP/2 can change connection multiplexing, proxy compatibility, and failure behavior for remote-write traffic.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use only after the receiver and every intermediary are proven compatible.

## Controls

- Set HTTP/2 behavior explicitly per endpoint.
- Canary while monitoring queue lag, retries, connection errors, CPU, and bytes.
- Keep sample checks unchanged.

## Implementation

- Change one endpoint at a time.
- Retain an HTTP/1.1 rollback.
- Document proxy/TLS requirements.

## Tests

- Test sustained load, reconnects, throttling, proxy restarts, and large backlogs.
- Compare delivered samples.

## Gotchas

- Multiplexing can concentrate failure.
- Some proxies mishandle long-lived streams.
- Protocol choice does not fix cardinality.

## Official sources

- [Official documentation](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#remote_write)
