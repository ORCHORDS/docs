# Rate Limits Do Not Replace Resource Budgets

**Issue:** An API has a requests-per-minute limit but one allowed request can still consume excessive CPU, memory, response size, upload bandwidth, batch work, or execution time.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

OWASP API4:2023 treats unrestricted resource consumption as broader than request frequency. Safe APIs bound the cost of individual requests as well as how often they may be made.

## Engineering rule

- Bound request body and upload sizes.
- Bound pagination, batch cardinality, query complexity, and generated response size.
- Apply execution deadlines and platform resource limits where available.
- Rate-limit repeated operations, but do not rely on rate limiting as the only consumption control.
- Measure rejected work by limit type so legitimate demand can be tuned without silently removing protections.

## Verification

- Exercise maximum-size uploads, page sizes, batch requests, and expensive query parameters.
- Confirm each dimension has a deterministic server-side cap.
- Load-test below the request-rate threshold and verify a single request shape cannot exhaust the service.

## Official source

- OWASP API4:2023 Unrestricted Resource Consumption: https://owasp.org/API-Security/editions/2023/en/0xa4-unrestricted-resource-consumption/
