# Governing W3C Baggage in Agent Telemetry

## Scope

W3C Baggage is an HTTP propagation mechanism for application-defined key-value properties. Unlike trace context, baggage values can be copied across many downstream calls and may be exposed to services outside the original trust zone. Agent platforms are especially prone to adding tenant, experiment, tool, or conversation metadata for convenience. This article defines when baggage is appropriate and how to prevent it becoming an uncontrolled data-distribution channel.

Baggage is not a secure session, policy token, or authenticated claim. Recipients can modify it, intermediaries can observe it, and the specification does not provide confidentiality or integrity. Any authorization or routing decision must use trusted identity and policy data obtained through appropriate mechanisms.

## Implementation workflow

Inventory all baggage producers and consumers. For every key, assign an owner, purpose, syntax, maximum length, allowed values, sensitivity class, propagation destinations, and expiry plan. Default to no baggage. Admit a key only when downstream propagation is necessary and ordinary span attributes or an internal request envelope cannot meet the need.

Create a registry with stable names and collision avoidance. Prefer opaque, low-cardinality operational categories over identifiers. A bounded workload class may be suitable while a prompt fragment, email, document name, access token, or conversation ID is not. Document how keys are removed at public and partner boundaries.

Parse the `baggage` header according to the W3C grammar and apply local limits before copying values. Normalize neither attacker input nor percent-encoded content into logs without safe decoding rules. Build a fresh outbound header from admitted entries rather than blindly forwarding the inbound string. When fan-out occurs, apply destination-specific filtering for each child request.

## Controls

Maintain an allowlist; unknown keys are dropped at ingress and never influence privileged behavior. Set tighter local limits than protocol maxima when appropriate for infrastructure. Reject or truncate according to a documented policy, ensuring truncation cannot convert one meaning into another. Bound key count, total bytes, and per-value bytes to limit resource consumption.

Prohibit personal data, secrets, free text, user-generated content, security labels, and raw resource identifiers. Do not use baggage to select an account, grant a scope, skip approval, or assert a tenant. If a correlation key is needed, use a random opaque value with server-side access checks and short retention. Configure proxies and telemetry agents consistently so a stripped key is not unexpectedly reintroduced.

## Validation evidence

Unit tests should cover grammar edge cases, duplicate keys, properties, percent encoding, empty members, oversized values, and unknown entries. Boundary tests should prove that sensitive and unregistered keys do not reach model providers or third-party tools. Inject canary baggage and inspect requests at every hop, including retries, queues, webhooks, and fallback routes.

Retain the registry history, approvals, gateway filtering configuration, test captures with values redacted, and scan reports from telemetry stores. Monitor key cardinality, dropped-entry counts, header size, and unexpected destination observations. Periodically search for patterns resembling credentials and personal identifiers. Confirm that disabling baggage does not break authorization; such a failure indicates an improper dependency.

## Failure handling

For malformed or excessive baggage, drop offending entries or the entire header and proceed with fresh local context when safe. Emit a rate-limited diagnostic containing key names only if those names meet logging policy. Never reflect raw baggage in an error response.

If sensitive data is found, stop propagation at the nearest gateway, disable the producer, identify downstream recipients and retained copies, and follow privacy or credential incident procedures. Rotate exposed secrets and delete telemetry where policy and backend capability permit. Replace the use case with span-local attributes or a controlled server-side lookup, then add a regression canary.

## Canonical sources

- W3C Baggage Recommendation: https://www.w3.org/TR/baggage/
- OpenTelemetry Baggage specification: https://opentelemetry.io/docs/specs/otel/baggage/api/
- OpenTelemetry security guidance: https://opentelemetry.io/docs/security/
