# A2A TCK Conformance Governance

## Purpose

The A2A Protocol Technology Compatibility Kit (TCK) is the official compatibility test suite maintained by the A2A project. It validates an A2A implementation across protocol requirements and supported transports and can provide repeatable evidence that implementation behavior matches the protocol requirements exercised by the suite.

## Current TCK model

The current TCK supports gRPC, JSON-RPC, and HTTP+JSON transports. It retrieves the system under test's Agent Card and uses declared interfaces and capabilities to decide which tests apply.

Tests are organized by normative requirement level:

- MUST requirements are hard compatibility failures when not met;
- SHOULD requirements are tracked as expected failures when an implementation intentionally differs; and
- MAY behavior is optional and can be skipped when the capability is not declared.

The project also groups tests by mandatory behavior, declared capabilities, quality, and optional features.

## Governance pattern

1. Pin the TCK revision or released version used for a compatibility decision.
2. Run mandatory requirements against every transport the implementation claims to support.
3. Run capability tests against every capability advertised in the Agent Card so declarations are not accepted without matching behavior.
4. Preserve machine-readable and human-readable TCK reports with the implementation revision under test.
5. Treat skipped tests as evidence to review, not automatically as success; confirm the associated capability is genuinely undeclared or not applicable.
6. Separate protocol compatibility from production-readiness testing such as load, resilience, privacy, abuse prevention, and deployment-specific security controls.
7. Re-run the TCK after protocol-version upgrades, transport changes, Agent Card capability changes, or major SDK/runtime upgrades.

## Authentication testing

The official TCK supports authenticated systems under test. Authentication configuration should use dedicated test credentials with least privilege and short lifetime where practical.

If an Agent Card declares security requirements, tests should verify that unauthenticated calls are actually rejected. Advertising authentication without enforcing it is an implementation defect, not merely a TCK configuration problem.

## Reports and evidence

Compatibility reports should record at least:

- A2A protocol version targeted;
- TCK commit or release identifier;
- system-under-test build/revision;
- tested transport(s);
- declared capabilities;
- mandatory failures;
- expected SHOULD-level deviations; and
- skipped optional/capability tests with reason.

## Failure modes

- Passing one transport does not establish compatibility for other transports advertised in the Agent Card.
- Ignoring skipped capability tests can hide false capability advertising.
- Treating quality-category findings as protocol MUST failures can misstate compatibility.
- Treating TCK compatibility as security certification overstates what the suite proves.
- Running an unpinned moving `main` revision makes historical results difficult to reproduce.

## Sources

- A2A Project — A2A Protocol Technology Compatibility Kit: https://github.com/a2aproject/a2a-tck
- A2A TCK — SDK Validation Guide: https://github.com/a2aproject/a2a-tck/blob/main/docs/SDK_VALIDATION_GUIDE.md
- A2A Protocol — latest specification: https://a2a-protocol.org/latest/specification/

## Scope note

The TCK validates behaviors represented by its test suite. It is not a certification, audit, or substitute for application-specific security, performance, and operational testing.