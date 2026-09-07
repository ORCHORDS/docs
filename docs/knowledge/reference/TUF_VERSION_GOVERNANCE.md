---
title: The Update Framework (TUF) Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-07
review-cycle: 180 days
next-review: 2027-03-06
source: https://theupdateframework.io/ ; https://github.com/theupdateframework/specification
---

# The Update Framework (TUF) Version Governance

## 1. Purpose

This reference card governs the lifecycle of the **Update Framework (TUF)** specification and reference implementations (python-tuf, go-tuf) used to secure artifact delivery for in-house package mirrors, container image registries, and CI tooling installers.

## 2. Scope

In scope:

- TUF specification v1.0 (2022) and current draft (v1.1 in development).
- Reference implementations: `python-tuf >= 5.x`, `go-tuf >= 2.x`.
- TUF-on-CI integrations: `sigstore-tuf`, `repository-tool` for private registries.
- Roles: root, timestamp, snapshot, targets, mirror.

Out of scope:

- The Update Framework's role-based cryptographic primitives (already covered in NIST SP 800-218A).
- npm/PyPI public mirrors (use the public TUF-based metadata services directly).

## 3. Versioning policy

- Pin TUF reference implementations to a known-good patch version (e.g. `python-tuf==5.1.0`) and verify by digest.
- TUF metadata is **content-addressed**; mirror keys MUST be rotated every 180 days.
- All roles MUST be configured with a 3-person quorum for the offline root key, 2-person for timestamp/snapshot, and 1-person for targets.
- Never serve unsigned metadata; always include the canonical JSON signature set.

## 4. Compatibility matrix

| TUF spec | python-tuf | go-tuf | Notes |
| --- | --- | --- | --- |
| 1.0 (2022) | 5.x | 2.x | Stable role delegation |
| 1.0.1 (2024 patch) | 5.1.x | 2.1.x | Added length-prefixed hash |
| 1.1 (draft) | not released | not released | Multi-repository delegation |

## 5. Metadata design

- **Root.json**: offline, signed by ≥ 3 of 5 hardware-backed root keys (YubiHSM2 or AWS CloudHSM).
- **Timestamp.json**: short expiry (≤ 24 h), online signing.
- **Snapshot.json**: 7-day expiry; signed automatically by repo tooling.
- **Targets.json**: 90-day expiry; named by logical repository, version, and architecture.
- **Delegations**: scopes defined by product team; max depth of 3.

## 6. Signing workflow

1. Maintainers commit target metadata to a private repo (`tuf-metadata/`).
2. CI runs `python-tuf sign` against the staging repo, producing `targets.json` + signed `snapshot.json`.
3. Release engineer rotates `timestamp.json` every 24 h via a separate pipeline.
4. Public mirror pulls via `tuf client` and verifies root is anchored to a pinned key ID.

## 7. Upgrade procedure

1. Verify the new TUF ref-impl release is signed and tagged by the maintainer.
2. Roll the offline root key threshold with `repository-tool change-root` if rotating keys.
3. Publish a new `root.json` to client bundles; clients must pick up the new root on next bootstrap.
4. Promote after 7 days of clean pulls; back out by re-publishing the previous `root.json`.

## 8. Rollback procedure

- Revert `repository-tool` to the previous version.
- Re-publish the previous `root.json` to clients via out-of-band bundle.
- Note: rollback is required because clients must trust whichever `root.json` is pinned locally.

## 9. Observability

- Required metrics: `tuf_metadata_sign_total{role,result}`, `tuf_metadata_fetch_total{role,result}`, `tuf_repo_size_bytes{role}`.
- Alert on `tuf_metadata_fetch_total{role="root",result="failure"}` > 0 sustained over 1 hour.

## 10. References

- TUF specification — https://theupdateframework.io/
- python-tuf — https://github.com/theupdateframework/python-tuf
- go-tuf — https://github.com/theupdateframework/go-tuf
