# GitHub Artifact Attestation Verification

## Purpose

GitHub artifact attestations create cryptographically signed provenance claims that let consumers verify where and how a build artifact was produced. The security value comes from verification and policy enforcement, not from generating an attestation alone.

## What an attestation establishes

GitHub's artifact attestation system can bind an artifact to provenance information such as the repository, organization, workflow, environment, commit SHA, triggering event, and other identity information derived from the GitHub Actions OIDC token.

An attestation does **not** prove that the artifact is safe or free of vulnerabilities. It provides evidence about origin and build context that a consumer can evaluate against its own policy.

## Verification workflow

For a released binary or OCI image:

1. Obtain the artifact from the intended distribution channel.
2. Identify the repository or owner that is expected to have produced it.
3. Run `gh attestation verify` against the artifact or image.
4. Constrain signer identity more precisely when policy requires it, for example with the signer workflow or signer repository.
5. Verify the expected predicate type when the attestation represents something other than the default SLSA provenance claim.
6. Treat verification output as input to a policy decision rather than as an automatic declaration that the software is trustworthy.

## Offline verification

GitHub also supports offline verification. A controlled offline process should export:

- the artifact;
- its attestation bundle;
- the required trusted-root material; and
- a compatible GitHub CLI environment.

Refresh trusted-root information when importing newly signed material into an offline environment because signing roots can rotate. Offline verification should preserve the bundle and trusted-root version used for the decision.

## What to attest

GitHub recommends generating attestations for released software that consumers are expected to verify, including binaries, downloadable packages, container images, or manifests representing detailed contents. It does not recommend signing every source file, documentation file, embedded image, or routine test build merely to increase attestation count.

## Sources

- GitHub Docs — Artifact attestations: https://docs.github.com/en/actions/concepts/security/artifact-attestations
- GitHub Docs — Using artifact attestations to establish provenance for builds: https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations
- GitHub Docs — Verifying attestations offline: https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/verify-attestations-offline

## Scope note

This article describes public GitHub artifact-attestation verification concepts. Repository permissions, Actions workflow design, SLSA policy, release approval, key trust, and artifact security remain separate controls.