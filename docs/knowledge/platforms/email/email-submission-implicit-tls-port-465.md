# Email submission over implicit TLS on port 465

**Issue:** A mail client treats ports 25, 465, and 587 as interchangeable, attempts plaintext before TLS, or authenticates after a failed STARTTLS negotiation. Credentials and message content can then cross an unauthenticated channel, while failures are hidden by insecure fallback.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Port and protocol boundary

RFC 8314 establishes implicit TLS for message submission on TCP port 465 (“submissions”). The TLS handshake begins immediately after connection; SMTP commands are not sent first. Port 587 remains the message-submission port commonly using explicit TLS through STARTTLS. Port 25 is primarily MTA-to-MTA relay and must not be selected as a credentialed client-submission fallback merely because submission failed.

Model these as explicit endpoint modes:

- `465 / implicit TLS`: TLS handshake, certificate validation, then SMTP and authentication.
- `587 / STARTTLS`: SMTP greeting and capability negotiation, successful STARTTLS, a fresh post-TLS SMTP negotiation, then authentication.
- `25 / relay`: a separately configured server role and policy.

Do not infer the mode only from a user-editable port when an endpoint profile can store both port and transport.

## Security controls

1. Validate the service identity against the configured hostname and a trusted certificate path. A successful encryption handshake with the wrong peer is failure.
2. Never send SASL credentials before the required TLS mode succeeds.
3. After STARTTLS, discard pre-TLS capability state and issue the required fresh SMTP greeting/capability exchange.
4. Do not downgrade from implicit TLS to plaintext or from failed STARTTLS to cleartext. Surface a diagnosable error.
5. Use current TLS policy and make obsolete protocol/cipher exceptions explicit, scoped, expiring compatibility overrides.
6. Keep proxy, DNS, and certificate errors distinct in telemetry. Redact credentials, authorization payloads, and message content.
7. Pinning is not a substitute for normal service-identity validation and requires a safe rotation path.

## Migration

Add port 465 implicit TLS as a first-class profile rather than silently rewriting every port-587 account. Discover or provision server settings, test certificate identity and authentication, then migrate in controlled cohorts. Retain an explicit, secure STARTTLS profile where required by the provider.

Measure connection success, TLS alerts, certificate failures, authentication failures, and downgrade attempts by provider and client version. A rollout is healthy only when success rises without any plaintext credential path.

## Verification

Use a test server to assert that port 465 receives a TLS ClientHello as the first bytes. For port 587, assert no authentication command occurs before successful STARTTLS and post-TLS renegotiation. Test stripped STARTTLS capability, invalid/expired/mismatched certificates, connection interception, TLS alerts, and an unavailable 465 endpoint. Every case must fail without plaintext fallback.

## Gotchas

- “SSL” UI labels often ambiguously mean implicit TLS; store the actual mode.
- Opportunistic relay TLS policy is not suitable for credentialed submission.
- TLS protects the hop, not end-to-end message confidentiality.
- Retrying another secure endpoint can be valid; silently changing to plaintext is not.

## Sources

- [RFC 8314 — Cleartext Considered Obsolete: Use of TLS for Email Submission and Access](https://www.rfc-editor.org/rfc/rfc8314.html)
