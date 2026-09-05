# Protobuf Schema Deprecation Playbook

## Purpose

Define the operational procedure for deprecating and removing a field, enum value, or RPC method in a Protobuf schema while maintaining backward compatibility. The procedure ensures that consumers running older generated code do not lose functionality.

## Audience

Service owners and API engineers who maintain `.proto` files and generated code.

## Pre-conditions

- The schema lives in a Buf-managed module (per `PROTOBUF_VERSION_GOVERNANCE.md`).
- The team has access to `buf` CLI.
- The team can ship generated code in lockstep with consumers.

## Procedure

### Step 1 — Identify the candidate

1. Inventory fields, enum values, and methods that are unused for at least 6 months.
2. Check usage via generated-code search, logs, or consumer surveys.
3. Confirm the field is not part of any documented public contract.

### Step 2 — Mark deprecated

4. Add `// deprecated: <reason>` to the field or method.
5. Add `[deprecated = true]` annotation in the `.proto`.
6. Bump the package version to `v1` (or maintain minor version).
7. Update generated code in lockstep with consumers.

### Step 3 — Communicate

8. Announce the deprecation in the API changelog.
9. Provide a 90-day migration window before deletion.
10. Track consumer usage in the deprecation period.

### Step 4 — Block reuse of field numbers

11. Move the deprecated field to `reserved`.
12. Add `reserved <field_number>;` in the message.
13. This blocks reuse of the tag in any future field.

### Step 5 — Remove

14. After 90 days, remove the deprecated field, enum value, or method.
15. Bump the package version to `v2` if breaking change.
16. Run `buf breaking --against <previous-tag>` to confirm.

### Step 6 — Verify

17. Run `buf lint`.
18. Run `buf build`.
19. Confirm consumers regenerate successfully.
20. Run integration tests.

## Rollback

If a removal breaks a consumer:

1. Re-introduce the field as deprecated (not as `reserved`).
2. Bump the version to reflect the regression.
3. Communicate immediately.

## References

- `PROTOBUF_VERSION_GOVERNANCE.md`
- Buf breaking: `https://buf.build/docs/lint/usage/`
- Proto3 language guide: `https://protobuf.dev/programming-guides/proto3/`
