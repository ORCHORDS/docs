# AsyncAPI 3 Operation, Channel, and Message Subsets

**Issue:** An AsyncAPI document can claim an application processes every message on a shared channel even when each operation supports only a subset.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Model channels as shared addresses and root operations as the actions the described application must implement.
- For each operation, reference exactly one channel and list only messages defined on that channel that the operation actually processes.
- Use `send` and `receive` from the described application's perspective; do not mechanically invert a consumer document to describe a producer.
- Keep protocol details in bindings and application semantics in operations and messages.
- Require every runtime message on a channel to validate against exactly one channel message definition.

## Verification

- Lint all operation channel and message references after dereferencing.
- Publish fixtures for every declared message and reject fixtures matching zero or multiple definitions.
- Compare generated producer and consumer code with the application's actual direction and broker permissions.

## Gotchas

- Validate feature and specification maturity against the cited official source.
- Avoid secrets, personal data, and restricted operational details in examples or evidence.
- Reassess after scope, dependency, protocol, or policy changes.

## Sources

- https://www.asyncapi.com/docs/reference/specification/v3.0.0
