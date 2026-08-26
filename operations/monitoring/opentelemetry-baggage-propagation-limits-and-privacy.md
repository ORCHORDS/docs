# OpenTelemetry baggage: propagation limits and privacy controls

**Category:** Monitoring
**Author:** ORCHORDS
**Primary source:** [OpenTelemetry Baggage](https://opentelemetry.io/docs/concepts/signals/baggage/)

## Problem

Baggage propagates key-value data across process boundaries independently of a trace. That makes it useful for routing and correlation, but it also means a value can reach services, vendors, and logs that the originating code did not anticipate.

## Practice

- Use baggage only for small, non-sensitive routing or correlation values with a documented consumer.
- Maintain an allowlist of keys that may cross each trust boundary; drop all others before outbound propagation.
- Never place credentials, session identifiers, payment data, health data, raw personal data, or high-cardinality user identifiers in baggage.
- Prefer a short opaque correlation ID over descriptive user or account fields, and ensure recipients cannot resolve it without authorization.
- Treat baggage changes as API changes: version them, test propagation, and document third-party destinations.
- Apply size limits and expiry semantics in application policy; do not depend on arbitrary propagation through every intermediary.

## Verification

1. Trace a request through internal and third-party outbound calls and record which baggage keys cross each boundary.
2. Confirm prohibited keys are removed before each boundary.
3. Confirm a baggage value is absent from logs, errors, and metrics unless an explicit safe projection is intended.
4. Load-test large or malformed baggage headers and confirm they are rejected or truncated predictably.

## Failure modes

- A convenience field becomes an uncontrolled cross-service data channel.
- Raw account or session values leak to telemetry vendors.
- Downstream code treats mutable baggage as an authorization signal.

## Related

- [OpenTelemetry Baggage](https://opentelemetry.io/docs/concepts/signals/baggage/)
