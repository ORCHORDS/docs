# OpenTelemetry Collector health-check readiness contract

**Issue**

A reachable health-check endpoint can be mistaken for proof that receivers, exporters, and pipelines are ready to carry telemetry.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Bind the health endpoint only to the intended network and configure an explicit path and port.
- Define readiness separately from process liveness and validate critical pipeline dependencies externally.
- Protect detailed status responses from information disclosure.
- Include the extension in the service extensions list and version its configuration with the collector distribution.

## Verification

1. Stop an exporter while the process remains alive and confirm the external readiness gate reacts.
2. Test bind conflicts, TLS or proxy behavior, shutdown, and restart.
3. Probe from the same network plane as the orchestrator.

## Gotchas

- HTTP 200 may represent process health rather than end-to-end delivery.
- An extension configured but not enabled under service extensions does not run.
- Public binding can expose component state.

## Official source

- [Official documentation](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/extension/healthcheckextension)
