# Paketo Buildpack Adoption Playbook

## Purpose

Migrate an application's OCI image build from a custom Dockerfile to a Cloud Native Buildpacks (Paketo) pipeline without losing reproducibility, SBOM coverage, or runtime performance.

## Audience

Build engineers, platform engineers, application teams migrating from manual Docker builds.

## Pre-conditions

- `pack` CLI ≥ 0.36 installed locally and on CI runners.
- Paketo builder image (`base` or `tiny`) mirrored to the platform OCI registry.
- Source tree supports buildpack detection — i.e. contains `pom.xml`, `package.json`, `go.mod`, `requirements.txt`, or equivalent.
- A non-production cluster or staging environment for the first image produced by the new pipeline.

## Procedure

1. **Detect**: run `pack builder suggest` and confirm a builder that matches the runtime (e.g. `paketobuildpacks/builder-jammy-base`).
2. **Build locally**: `pack build <image> --builder <pinned-builder-digest> --tag <dev-tag>`. Inspect `/layers`, `/workspace`, and the produced SBOM (`<image>.sbom.cdx.json`).
3. **Compare**: run the resulting image against the previous Dockerfile image on the same workload for at least one business cycle. Compare image size, cold-start latency, and SBOM completeness.
4. **Wire CI**: add a Tekton task that invokes the lifecycle with `--previous-image`, `--cache-image`, and `--sbom-output-dir`. Mount the OCI registry credentials via `ServiceAccount`.
5. **Sign**: integrate Cosign sign + verify tasks. Add an attestation publisher for `https://in-toto.io/attestation/v1` provenance.
6. **Rebase**: enable `pack rebase` for routine base-image security patches. Document the rebaser in the platform runbook.
7. **Cutover**: switch the application's deployment pipeline to pull from the new image digest. Keep the old Dockerfile image available for a 14-day rollback window.
8. **Decommission**: after 14 green days, archive the Dockerfile and remove the legacy CI build step.

## Rollback

- Re-point deployment manifests to the legacy image digest. No application code changes are required because Paketo produces images that respect the run-image contract.
- Disable the buildpacks CI tasks without deleting the workflow so re-enabling takes minutes, not hours.

## References

- Paketo documentation — https://paketo.io/docs/
- Buildpacks lifecycle reference — https://buildpacks.io/docs/concepts/components/lifecycle/
- Internal: Batch 98 reference card `PAKETO_BUILDPACKS_GOVERNANCE.md`.
