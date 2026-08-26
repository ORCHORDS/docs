# Docker Compose app-protocol metadata contract

**Problem**

Port numbers and transport alone do not express the application protocol expected by Compose consumers.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use when deployment tooling interprets service port semantics.

## Controls

- Set `app_protocol` only to a standardized or governed value.
- Keep actual TLS and authentication configuration authoritative.
- Version every consumer relying on the metadata.

## Implementation

- Declare it beside target, published, and transport fields.
- Validate the effective Compose model.
- Never infer security from metadata.

## Tests

- Test known and unknown values across supported Compose versions.
- Probe the real endpoint protocol independently.

## Gotchas

- Metadata does not configure the service.
- Support varies by implementation.
- Wrong metadata can misroute tooling.

## Official sources

- [Compose service ports](https://docs.docker.com/reference/compose-file/services/#ports)
