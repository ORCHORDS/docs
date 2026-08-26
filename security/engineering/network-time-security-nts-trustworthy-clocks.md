# Network Time Security for trustworthy clocks

**Category:** Security
**Author:** ORCHORDS
**Primary source:** [RFC 8915: Network Time Security for NTP](https://www.rfc-editor.org/rfc/rfc8915.html)

## Problem

Time affects token validation, signed requests, certificate checks, event ordering, and incident investigation. Unauthenticated NTP can be manipulated by a network adversary, causing authentication failures or weakening time-based security controls.

## Practice

- Identify systems where clock integrity materially affects authorization, financial records, audit evidence, or distributed coordination.
- Use Network Time Security (NTS) capable clients and servers where supported. NTS establishes keys over TLS and authenticates NTP synchronization traffic.
- Configure multiple approved time sources and monitor offset, synchronization state, source changes, and sudden clock steps.
- Define a bounded response to unacceptable skew: fail closed for high-risk verification, queue or degrade noncritical work, and alert operators.
- Keep time-service certificate validation and NTS configuration under normal certificate and configuration-change control.
- Do not treat NTS as a replacement for application replay protection; it improves clock trust, not every protocol property.

## Verification

1. Simulate a source outage, large offset, and time step; confirm alerts and application behavior match the skew policy.
2. Confirm the client verifies NTS service identity and refuses downgrade to an unapproved source.
3. Test authentication, certificate validation, and scheduled jobs near the permitted skew boundary.
4. Review production telemetry for source diversity and offset drift.

## Failure modes

- One unauthenticated time source becomes a single point of compromise.
- A clock correction invalidates tokens or signatures without detection.
- Time drift is discovered only through application failures rather than direct clock monitoring.

## Related

- [RFC 8915](https://www.rfc-editor.org/rfc/rfc8915.html)
