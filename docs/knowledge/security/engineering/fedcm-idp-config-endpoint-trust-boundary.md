# FedCM IdP configuration endpoint trust boundary

**Issue:** FedCM fetches IdP configuration and endpoints through browser-mediated discovery; metadata is not application authorization.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Pin expected IdP origins, HTTPS, exact endpoint relationships, token validation, account/session separation.

## Tests

Redirects, cross-origin endpoints, stale config, compromised metadata, unsupported browser, logout.

## Gotchas

FedCM reduces cross-site exposure but does not replace OIDC/token validation or IdP compromise handling.

## Official sources

- https://w3c-fedid.github.io/FedCM/
