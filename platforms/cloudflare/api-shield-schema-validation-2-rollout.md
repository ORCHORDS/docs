# api-shield-schema-validation-2-rollout

**Issue:** API schema validation is enabled in blocking mode before the team has an owned inventory, representative traffic evidence, and endpoint-specific rollback plan.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Root cause

An OpenAPI schema is a security control only when it describes the deployed API. Enforcing an incomplete schema can block legitimate traffic; leaving it in observation forever provides no protection. Cloudflare API Shield combines discovery with schema validation, so rollout must move from inventory to logging to targeted enforcement.

**Source:** [Cloudflare schema validation](https://developers.cloudflare.com/api-shield/security/schema-validation/) and [API Discovery](https://developers.cloudflare.com/api-shield/security/api-discovery/).

## Fix

- assign an owner and OpenAPI contract for every exposed endpoint;
- compare discovered traffic with the contract and resolve intentional variants;
- begin in logging/observation mode and capture representative legitimate traffic;
- add synthetic negative tests for undeclared fields, methods, content types, and malformed bodies;
- enable blocking per endpoint after review, with a documented rollback and Security Events monitoring;
- track schema changes in the same review path as API changes.

## Verification

- Legitimate production-like requests pass in observation and enforcement modes.
- A contract-violating request is logged, then blocked for the intended endpoint.
- A rollback restores service without removing the contract evidence.
- New endpoint deployment fails review when no owner/schema is supplied.

## Related

- `security/owasp-api-top-10-2023.md`
- `cloudflare/waf-rate-limiting-deep-dive.md`
