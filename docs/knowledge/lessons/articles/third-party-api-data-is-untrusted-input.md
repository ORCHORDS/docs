# Third-Party API Data Is Untrusted Input

**Issue:** Data received from a reputable external API bypasses normal validation because developers assume the provider is trustworthy.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

OWASP API10:2023 highlights that attackers may compromise or manipulate integrated services and use trusted-data assumptions against the consuming application. External API responses can carry malicious, malformed, oversized, or unexpected data just like direct user input.

## Engineering rule

- Validate external API responses before storage, rendering, query construction, or downstream execution.
- Enforce expected types, ranges, lengths, formats, and schemas.
- Encode or parameterize data at the sink instead of trusting upstream sanitization.
- Treat provider reputation as a supply-chain consideration, not an input-validation bypass.
- Bound response size and processing work.

## Verification

- Substitute malformed and adversarial third-party responses in integration tests.
- Confirm downstream database, template, command, and parser boundaries remain safe.
- Verify unexpected fields and oversized payloads are rejected or safely ignored according to contract.

## Official source

- OWASP API10:2023 Unsafe Consumption of APIs: https://owasp.org/API-Security/editions/2023/en/0xaa-unsafe-consumption-of-apis/
