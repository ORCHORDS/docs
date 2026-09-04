# Third-Party API Consumption Review

## Trigger
Run before integrating a new external API, when its contract or provider changes materially, and during periodic dependency-security review.

## Inputs
- External API contract/schema.
- Authentication and transport configuration.
- Redirect behavior.
- Request/response limits and deadlines.
- Downstream sinks that consume provider data.

## Procedure
1. Document the data and trust boundary for the external integration.
2. Verify encrypted transport and certificate validation according to the client/platform policy.
3. Define expected response types, ranges, lengths, formats, and maximum sizes.
4. Validate provider responses before they reach storage, rendering, query construction, command execution, or other sensitive sinks.
5. Define whether redirects are permitted; if they are, constrain destinations and re-evaluate forwarding of credentials or sensitive bodies.
6. Configure bounded connection/operation deadlines and resource limits appropriate to the integration.
7. Inject malformed, oversized, unexpected, and adversarial provider responses in tests.
8. Simulate slow responses and redirects to unexpected hosts and verify safe failure behavior.
9. Record provider-contract assumptions and monitoring signals for invalid responses, timeout, or redirect rejection.

## Escalation
Escalate any integration that requires trusting unvalidated provider data, forwarding credentials to uncontrolled redirect destinations, or operating without bounded resource/deadline behavior.

## Evidence
- Integration trust-boundary record.
- Schema/validation tests.
- Redirect-policy tests.
- Timeout/resource-limit tests.
- Findings and remediation evidence.

## Completion criteria
External API data is treated as untrusted input, redirects are policy-controlled, and consumption is bounded by explicit validation and resource/deadline controls.

## Source basis
- OWASP API10:2023 Unsafe Consumption of APIs: https://owasp.org/API-Security/editions/2023/en/0xaa-unsafe-consumption-of-apis/
