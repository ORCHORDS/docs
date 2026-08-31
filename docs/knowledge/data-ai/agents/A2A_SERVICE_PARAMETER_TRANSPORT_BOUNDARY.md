# A2A Service Parameter Transport Boundary

## Purpose

A2A v1.0 separates operation payload metadata from service parameters that apply horizontally across a request. Service parameters travel through the protocol binding rather than as ordinary message or task content.

## Core distinction

A2A operation `metadata` is a flexible key-value map carried with protocol objects. Service parameters are different: they are case-insensitive string keys with case-sensitive string values whose transmission mechanism is defined by the selected protocol binding.

Implementations should not silently move service parameters into message parts, task metadata, or artifact metadata because doing so can change interoperability and security semantics.

## Standard service parameters

The v1.0 specification defines standard parameters including:

- `A2A-Version` — identifies the A2A protocol version used by the client; unsupported versions produce `VersionNotSupportedError`.
- `A2A-Extensions` — lists extension URIs the client wants to use for the request.

A2A-defined service parameter names use the `a2a-` prefix so they can coexist with transport- or infrastructure-specific parameters.

## Binding requirements

For HTTP-based bindings, service parameters map to HTTP header fields. For gRPC, they are carried as gRPC metadata and parameter names are normalized according to gRPC header conventions. A custom protocol binding must explicitly define how service parameters are transported.

A reusable binding implementation should:

1. extract service parameters before dispatching the operation;
2. preserve the distinction between transport context and application payload;
3. validate required protocol-version and extension declarations;
4. avoid logging authentication or other sensitive transport context indiscriminately;
5. normalize keys only where the binding requires it; and
6. preserve semantically equivalent behavior across supported bindings.

## Custom bindings

A custom A2A binding needs to specify the data mappings, service-parameter mechanism, error mapping, and streaming behavior needed to preserve the core protocol's semantics. Transports without native headers can use a dedicated transport metadata structure, but that structure should remain separate from ordinary A2A content.

## Sources

- A2A Protocol v1.0 — Core specification, Service Parameters: https://a2a-protocol.org/latest/specification/
- A2A Protocol — Custom Protocol Bindings: https://a2a-protocol.org/latest/topics/custom-protocol-bindings/

## Scope note

Service parameters are a protocol transport concept, not a general-purpose place for arbitrary secrets. Authentication, tracing, tenant routing, and extension-specific values must follow the relevant binding and security design.