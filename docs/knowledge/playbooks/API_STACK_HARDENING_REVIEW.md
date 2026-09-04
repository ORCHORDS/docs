# API Stack Hardening Review

## Trigger
Run for new API deployments, infrastructure migrations, major framework/gateway upgrades, and periodic configuration review.

## Inputs
- Request path from client through gateway/proxy/load balancer to application and downstream services.
- Environment configuration baselines.
- TLS, CORS, security-header, method, permission, and error-handling settings.

## Procedure
1. Diagram every component that receives, terminates, forwards, parses, or authorizes API traffic.
2. Compare each component against its approved hardening baseline.
3. Disable unnecessary services, methods, features, accounts, ports, and legacy behavior.
4. Verify TLS requirements across client-facing and service-to-service API links as applicable.
5. Review browser-facing CORS and security-header configuration.
6. Trigger representative error paths and confirm public responses do not expose stack traces or internal diagnostics.
7. Send unexpected methods, content types, duplicate headers, and ambiguous requests through the complete request chain and compare interpretation across layers.
8. Record drift and retest after remediation or upgrades.

## Escalation
Escalate configuration drift that creates unauthorized exposure, weak transport, inconsistent request interpretation, or disclosure of sensitive implementation detail.

## Evidence
- Request-chain diagram.
- Baseline comparison results.
- Error-response samples.
- Request-parsing test results.
- Findings and remediation records.

## Completion criteria
Every request-chain component conforms to the intended hardening baseline and interprets security-relevant requests consistently enough to preserve the API security policy.

## Source basis
- OWASP API8:2023 Security Misconfiguration: https://owasp.org/API-Security/editions/2023/en/0xa8-security-misconfiguration/
