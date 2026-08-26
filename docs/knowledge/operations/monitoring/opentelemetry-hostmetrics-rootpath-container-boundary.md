# OpenTelemetry hostmetrics root-path boundary

**Issue**

A containerized hostmetrics receiver needs an explicit host filesystem view; the wrong root silently reports container data as host data.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Mount only required host paths read-only.
- Set root_path explicitly and label collection scope.
- Keep host PID/network permissions minimal.

## Verification

1. Compare collector data with host-native tools.
2. Test missing and partial mounts.
3. Verify container and host identities cannot merge.

## Gotchas

- Root path does not grant every kernel metric.
- Mounts expose host information.
- Platform scrapers differ.

## Official source

- [Official documentation](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/hostmetricsreceiver)
