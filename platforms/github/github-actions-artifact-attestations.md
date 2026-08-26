# github-actions-artifact-attestations

**Issue:** Release artifacts cannot be tied to a specific reviewed workflow and source revision
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Symptom

A release binary, package, container image, or manifest has a checksum but consumers cannot independently establish which repository revision and build workflow produced it.

## Root cause

A checksum proves only that two byte streams match. It does not establish build provenance. GitHub artifact attestations produce cryptographically signed provenance claims linked to the workflow, repository, commit SHA, triggering event, and OIDC identity. Their security value exists only when a consumer verifies the attestation and enforces an expected identity and source policy.

**Source:** [GitHub Docs — Artifact attestations](https://docs.github.com/en/actions/concepts/security/artifact-attestations).

## Fix

For each distributable artifact:

- build in a protected release workflow and pin third-party Actions to immutable commit SHAs;
- grant the workflow the minimum required permissions, including `attestations: write` and `id-token: write` only to the job that generates provenance;
- generate an attestation after the final artifact digest is known, optionally including an SBOM;
- publish the artifact digest alongside release metadata;
- verify before deployment or consumption with `gh attestation verify`, restricting the acceptable repository, workflow identity, subject digest, AND source digest (`--source-digest` to enforce the exact reviewed commit SHA, plus `--signer-digest` to pin the workflow revision — without these, any commit running the same workflow produces a valid attestation);
- retain a policy decision for verification failures: block by default, with an auditable emergency exception process.

## Verification

- **Positive:** a release artifact verifies against the expected repository, workflow, and digest.
- **Negative:** a modified artifact, a digest from another repository, and an attestation from an unapproved workflow each fail policy.
- **Review:** the attestation job has no unrelated write permissions or production deployment credentials.

## Gotchas

- An attestation is provenance evidence, not proof that the artifact is secure.
- Do not attest every transient CI output; prioritize artifacts users will run, download, or deploy.
- Public and private repositories use different Sigstore service arrangements; test verification in the intended consumer environment.

## Related

- `security/slsa-supply-chain.md`
- `security/supply-chain-npm-security.md`
- `github/github-actions-oidc-cloudflare.md`
