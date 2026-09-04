# API Error Responses Need Schema and Disclosure Controls

**Issue:** Success responses are schema-controlled, but exceptional paths return framework-generated errors that expose stack traces or other internal information.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

OWASP API8:2023 recommends defining and enforcing response payload schemas, including error responses, to prevent sensitive implementation information from reaching attackers. Error paths are part of the public API surface and need the same design discipline as successful responses.

## Engineering rule

- Define allowed error representations explicitly.
- Translate framework and dependency exceptions into controlled public errors.
- Keep stack traces, internal paths, queries, and private diagnostics in protected telemetry.
- Validate error payloads against the intended schema.
- Test configuration changes and upgrades for regression to verbose defaults.

## Verification

- Trigger validation errors, authentication failures, authorization failures, dependency failures, and unexpected exceptions.
- Scan every response for stack traces, internal paths, framework details, and sensitive values.
- Confirm the public schema remains stable while server-side logs preserve diagnostic context.

## Official source

- OWASP API8:2023 Security Misconfiguration: https://owasp.org/API-Security/editions/2023/en/0xa8-security-misconfiguration/
