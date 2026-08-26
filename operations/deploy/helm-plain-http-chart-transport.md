# Helm plain-HTTP chart transport boundary

**Problem**

Allowing plain HTTP for chart retrieval removes transport confidentiality and server authentication.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use only for isolated local registries with an independently authenticated artifact path.

## Controls

- Keep `--plain-http` disabled for production.
- Require chart signature/provenance or digest verification.
- Constrain network routes and repository configuration.

## Implementation

- Separate development and release commands.
- Log chart digest without credentials.
- Migrate internal registries to TLS.

## Tests

- Attempt MITM/substitution in a lab.
- Test redirects, credentials, provenance failure, and offline cache.

## Gotchas

- HTTP exposes chart names and credentials.
- Integrity alone does not hide content.
- Registry flags vary by Helm command.

## Official sources

- [Official documentation](https://helm.sh/docs/helm/helm_pull/)
