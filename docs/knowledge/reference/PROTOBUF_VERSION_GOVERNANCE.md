---
title: Protocol Buffers (Protobuf) Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: Protocol Buffers documentation; Google; protobuf.dev; language guides (C++, Java, Python, Go, C#, JS, etc.)
---

# Protocol Buffers (Protobuf) Version Governance

## Scope

This card governs how `orchords-docs` evaluates Protocol Buffers (`.proto`, `protoc`, generated code) across versions, languages, and wire compatibility. It is the reference input for any KB card that touches gRPC, schema evolution, or binary serialization.

## Why this card exists

Protocol Buffers power gRPC, Cloud APIs, and most modern service-to-service wire formats. Without an explicit card, the KB cites protobuf practices that ignore proto3 vs proto2, edition 2023/2024, and breaking-change semantics.

## Versions

| Edition / Version | Status |
|---|---|
| proto2 | legacy, still supported |
| proto3 | current, default |
| Edition 2023 | supported |
| Edition 2024 | supported |

References: `https://protobuf.dev/editions/`.

## Editions

Protobuf introduces editions (a successor to syntax versioning):

- `proto2` / `proto3` — classic syntax.
- `edition = "2023"` — editions syntax.
- `edition = "2024"` — editions syntax.

Editions are designed to be a non-breaking migration path; existing `proto2` / `proto3` files continue to work.

References: `https://protobuf.dev/editions/intro/`.

## Wire format and compatibility

| Field type | Wire-compatible rule |
|---|---|
| `optional` / `singular` | serialized tag is required to keep the field |
| `repeated` | append-only |
| `map<K,V>` | wire-equivalent to repeated message |
| `oneof` | only one field set at a time |
| `reserved` | block future reuse of tag numbers |

Rules:

1. Never change a field number without `reserved`.
2. Never change a field's wire type.
3. Never rename a field (semantics, not wire).
4. Adding fields is backward-compatible.
5. Removing fields requires `reserved` to prevent reuse.

## Code generation

| Toolchain | Status |
|---|---|
| `protoc` | reference C++ compiler |
| `buf` | modern build / lint / breaking-change tool |
| `protoc-gen-grpc-*` | gRPC codegen |
| `buf generate` | proto-to-code generation |

References: `https://buf.build/`.

## Recommended build pipeline

1. **Schema** lives in `proto/<org>/<service>/v1/<file>.proto`.
2. **Buf** module: `buf.yaml` + `buf.lock` pin dependencies.
3. **Lint** with `buf lint` (breaking rules).
4. **Generation** with `buf generate`.
5. **Breaking-change** check with `buf breaking --against <git-ref>`.
6. **Distribute** via Buf Schema Registry (BSR) or internal mirror.

## Schema versioning

| Pattern | When |
|---|---|
| package path `v1` | initial release |
| package path `v2` | breaking change |
| edition bump | non-breaking evolution |

## Cross-reference

| Domain | Card |
|---|---|
| gRPC | `GRPC_VERSION_GOVERNANCE.md` |
| Kafka | `KAFKA_KIP_VERSION_GOVERNANCE.md` |
| Service mesh | `ISTIO_VERSION_GOVERNANCE.md` |

## Sources

- Protobuf documentation: `https://protobuf.dev/`
- Editions: `https://protobuf.dev/editions/`
- Buf: `https://buf.build/docs/`
- Style guide: `https://protobuf.dev/programming-guides/style/`
