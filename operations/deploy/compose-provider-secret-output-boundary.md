# Compose provider output secret boundary

**Issue**

Provider-generated environment values can carry credentials into dependent services and diagnostics.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Classify provider output and expose only required keys.
- Avoid printing provider responses or resolved Compose configuration.
- Rotate external credentials on teardown and failure.

## Verification

1. Seed canary secrets and scan logs, inspect, and crash output.
2. Test dependency restart and provider failure.
3. Verify unrelated services cannot read values.

## Gotchas

- Environment variables are observable inside the container.
- Teardown may not run after host loss.
- Redaction must cover provider tooling too.

## Official source

- [Official documentation](https://docs.docker.com/reference/compose-file/services/#provider)
