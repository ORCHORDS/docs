# IETF RFC 9000 QUIC Transport Protocol Governance

## Purpose

IETF RFC 9000 specifies the QUIC transport protocol, providing reliable, secure, multiplexed connections over UDP. Governance ensures that an organization deploying QUIC uses the protocol correctly, maintains TLS 1.3 conformance per RFC 9001, and addresses performance, observability, and operational considerations.

## Current context and source status

RFC 9000 was published in May 2021, formalizing QUIC as an Internet Standard. Companion RFCs cover TLS 1.3 integration (RFC 9001), header compression (RFC 9204), and additional features. RFC 9221 (Bootstrapping WebSockets over HTTP/3) and RFC 9298 (CONNECT-UDP) are additional companion RFCs. Verify the current IETF publications before treating any specific QUIC feature as a current requirement.

## Governance workflow and controls

### 1. Implement RFC 9000 core

Implement RFC 9000 with the required features: connection establishment, stream multiplexing, flow control, congestion control, packet handling, error handling.

### 2. Use RFC 9001 TLS 1.3

Use RFC 9001 to integrate TLS 1.3. Verify peer certificates. Use only TLS 1.3 cipher suites permitted by the implementation.

### 3. Apply RFC 9204 QPACK

Apply RFC 9204 QPACK for header compression. Configure QPACK encoder/decoder streams. Apply table size limits.

### 4. Use HTTP/3 with QUIC

Use HTTP/3 (RFC 9114) for HTTP semantics on QUIC. Apply HTTP/3 framing.

### 5. Configure congestion control

Configure congestion control per RFC 9002 or the implementation's default. Document the choice.

### 6. Configure connection migration

Allow clients to migrate connections (RFC 9000 § 9). Configure connection IDs.

### 7. Implement observability

Implement observability per RFC 9000 § 19 (logging) and the QUIC debug log format. Track connection states, packet loss, and stream scheduling.

### 8. Address middlebox traversal

Address middlebox traversal. UDP port 443 is the standard. Use UDP-friendly congestion control.

## Validation and evidence

- Implementation conformance report.
- TLS 1.3 conformance test results.
- Performance benchmarks.
- Observability configuration.

## Failure correction

Common defects include disabling connection migration, weak TLS configuration, and missing observability. Corrective actions include a connection migration review, a TLS configuration audit, and an observability implementation plan.

## Limitations

- QUIC is UDP-based; some middleboxes interfere.
- QUIC implementations vary in performance and features.
- QUIC over IPv4/IPv6 dual stack requires careful address selection.
- Some legacy network monitoring tools do not understand QUIC.

## Canonical sources

- IETF RFC 9000, QUIC: A UDP-Based Multiplexed and Secure Transport, 2021.
- IETF RFC 9001, Using TLS to Secure QUIC, 2021.
- IETF RFC 9002, QUIC Loss Detection and Congestion Control, 2021.
- IETF RFC 9114, HTTP/3, 2022.
- IETF RFC 9204, QPACK: Field Compression for HTTP/3, 2022.

## Scope note

This article belongs to the reference leaf and cross-references the engineering leaf for protocol implementation, the platforms leaf for load balancing, and the operations leaf for protocol observability.
