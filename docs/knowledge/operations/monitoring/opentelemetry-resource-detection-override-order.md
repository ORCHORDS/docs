# OpenTelemetry resource-detection override order

**Issue**

Multiple resource detectors can produce the same attributes; detector order and override settings determine which identity reaches backends.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Define detector order and `override` behavior explicitly.
- Protect authoritative service identity from host/cloud detector replacement.
- Treat cloud metadata endpoints as privileged inputs and bound their timeouts.

## Verification

1. Replay conflicting attributes and assert final resources.
2. Run inside and outside each cloud environment.
3. Simulate metadata timeout and malformed responses.

## Gotchas

- Detector availability differs by distribution.
- Wrong resource identity fragments or merges telemetry.
- Adding a detector can change existing attributes.

## Official source

- [Official documentation](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/resourcedetectionprocessor)
