# A2A Capability Validation

## Purpose

A2A v1.0 uses Agent Card capability declarations to tell clients which optional protocol features an agent supports. Servers should reject unsupported optional operations predictably instead of silently degrading or accepting unusable configuration.

## Controls

1. Keep Agent Card capability declarations synchronized with deployed behavior.
2. Validate capability requirements before executing optional operations.
3. Reject push-notification configuration operations when push notifications are not advertised.
4. Reject streaming-dependent operations when streaming is not supported.
5. Return the protocol-defined or binding-appropriate error rather than silently ignoring an unsupported request.
6. Add conformance tests that compare advertised capabilities with actual endpoint behavior after releases.
7. Treat capability removal or addition as a compatibility change that requires client testing.

## Source

- A2A Protocol v1.0 specification, Capability Validation: https://a2a-protocol.org/dev/specification/

## Scope note

Capability validation establishes protocol consistency; it does not itself authorize a caller to use a supported capability.
