# GitHub Actions id-token permission job scope

**Issue:** `id-token: write` only permits requesting an OIDC token; cloud access depends on external trust policy, and broad job scope raises exposure.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Grant per job, restrict subject/audience/ref/environment in provider, use short sessions and no static fallback.

## Tests

Fork PR, wrong audience/ref, reusable workflow, environment approval, replay after expiry.

## Gotchas

OIDC tokens can be exfiltrated by any untrusted step in the permitted job.

## Official sources

- https://docs.github.com/en/actions/concepts/security/openid-connect
