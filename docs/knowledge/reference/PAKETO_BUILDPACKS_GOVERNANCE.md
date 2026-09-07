---
title: Cloud Native Buildpacks (Paketo) Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-07
review-cycle: 180 days
next-review: 2027-03-06
source: https://buildpacks.io ; https://paketo.io ; https://github.com/paketo-buildpacks
---

# Cloud Native Buildpacks (Paketo) Version Governance

## 1. Purpose

This reference card governs the lifecycle, version pinning, and supply-chain integrity of the Paketo Buildpacks distribution of Cloud Native Buildpacks. It applies to platform engineering teams that produce OCI images from source using `pack`, `kpack`, or Tekton `buildpacks` task.

## 2. Scope

In scope:

- Paketo **builder** images (base, full, tiny) tagged to the platform builder registry.
- Paketo **buildpack** lifecycle and dependency locking for Java, Node.js, Go, Python, .NET Core, PHP, Ruby, and static-file stacks.
- The Buildpacks **lifecycle** phases (`detect`, `analyze`, `restore`, `build`, `export`, `rebase`) and platform API compatibility.
- `pack` CLI ≥ 0.36 and `lifecycle` ≥ 0.20.

Out of scope:

- Heroku-style non-Paketo buildpacks where the lifecycle does not match CNB v3.

## 3. Versioning policy

- Builder images follow `<distro>-<stack>-<paketo-version>-<revision>` semantics. Pin to a specific revision (digest); the floating tag is restricted to staging clusters.
- Buildpack dependency versions are pinned in `package.toml` with `version = "x.y.z"` and an explicit SHA-256 of the upstream artefact.
- Lifecycle binaries (`lifecycle`, `pack`, `creator`, `detector`, `exporter`, `rebaser`) must all share a compatible platform API version (currently 0.12 / 0.13) before being installed together.

## 4. Compatibility matrix

| Component | Pinned version | Released | Notes |
| --- | --- | --- | --- |
| `pack` CLI | 0.36.4 | 2025-Q4 | Default `pack builder suggest` output |
| `lifecycle` | 0.20.x | 2025-Q4 | Supports Buildpack API 3.7 |
| `base-builder` (ubuntu-22.04) | 0.4.486 | 2025-Q4 | Replaces deprecated `full` |
| `tiny-builder` (distroless) | 0.4.486 | 2025-Q4 | Use for SBOM minimal footprint |
| Paketo Java buildpack | 13.7.x | 2025-Q4 | Java 8, 11, 17, 21 |
| Paketo Node.js buildpack | 12.6.x | 2025-Q4 | Node 18, 20, 22 |

## 5. Reproducibility and SBOM

- Always pass `--previous-image` and `--cache-image` to the lifecycle to enable layer reuse and deterministic rebases.
- Emit an SBOM in **Syft JSON** and **CycloneDX JSON** via `paketo build --sbom-output-dir`.
- Sign the resulting image with Cosign keyless; attach a `https://in-toto.io/attestation/v1` predicate for build provenance.

## 6. Upgrade procedure

1. Pull the new builder digest, verify its signature against the Paketo root key, and tag it into the platform builder registry.
2. Re-run a representative build matrix (Java, Node, Go, Python) against the new builder.
3. Compare SBOM diff against the previous builder; investigate any new direct or transitive dependency.
4. Promote the builder to the production builder namespace only after SBOM diff sign-off.

## 7. Rollback procedure

- Re-pin the platform builder to the previous known-good digest. Existing images built against the new builder remain valid; only future builds switch back.
- Use `pack rebase <existing-image>` to move workloads from a deprecated run-image to the previous run-image without rebuilding from source.

## 8. Observability

- Required metrics: `lifecycle_phase_duration_seconds{phase=...}`, `cache_layer_reuse_ratio`, `rebase_total{outcome=success|failure}`.
- Alert on `increase(lifecycle_export_failures_total[15m]) > 0` and on `cache_layer_reuse_ratio < 0.6` over a 24-hour window.

## 9. References

- Cloud Native Buildpacks specification — https://buildpacks.io/spec/
- Paketo Buildpacks release notes — https://github.com/paketo-buildpacks/paketo-release-notes
- Buildpacks lifecycle reference — https://buildpacks.io/docs/concepts/components/lifecycle/
