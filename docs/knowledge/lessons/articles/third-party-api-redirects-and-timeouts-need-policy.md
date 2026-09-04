# Third-Party API Redirects and Timeouts Need Policy

**Issue:** An integration blindly follows redirects and waits without bounded deadlines, allowing a compromised or misbehaving provider to redirect sensitive requests or consume unbounded resources.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

OWASP API10:2023 specifically calls out blind redirect following, missing resource limits, and missing timeouts when consuming other APIs. Redirect behavior and deadline handling are part of the trust boundary, not convenience defaults.

## Engineering rule

- Define whether redirects are allowed for each integration.
- If redirects are required, allowlist acceptable destinations and re-evaluate credentials and sensitive bodies before forwarding.
- Set bounded connection and operation deadlines appropriate to the dependency.
- Limit response size and processing resources.
- Classify timeout, redirect rejection, transport failure, and invalid response separately in telemetry.

## Verification

- Return a redirect to an attacker-controlled or unexpected host and confirm the client refuses it.
- Test redirects that would replay sensitive request bodies or authorization material.
- Simulate a slow or non-terminating provider and verify the deadline releases resources predictably.

## Official source

- OWASP API10:2023 Unsafe Consumption of APIs: https://owasp.org/API-Security/editions/2023/en/0xaa-unsafe-consumption-of-apis/
