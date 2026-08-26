# Software Supply Chain Security — SLSA, Sigstore, and Artifact Integrity

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

You publish npm packages, Docker images, or build artifacts but cannot
prove who built them, from what source code, or whether they were
tampered with after build. A compromised CI runner could inject
malicious code into your release artifacts without detection. Your
dependency tree includes 500+ transitive packages from unknown
maintainers, any of which could be compromised (SolarWinds, Codecov,
ua-parser-js, event-stream). You have no verification mechanism to
confirm that the artifact a customer downloads is the same one your CI
pipeline built.

## Context

Software supply chain security ensures the integrity and provenance of
software artifacts from source code to deployment. SLSA (Supply-chain
Levels for Software Artifacts, pronounced "salsa") is a framework of
incremental security levels (L0-L4) that define build integrity
requirements. Sigstore provides free, transparent code signing and
verification using ephemeral certificates tied to OIDC identities (no
long-lived signing keys to manage). In 2026, SLSA L3 is the target for
most organizations, GitHub Actions and GitLab CI produce SLSA L3
provenance natively, and Sigstore is the default signing mechanism for
npm, PyPI, Homebrew, and Kubernetes. The 2024-2026 wave of supply chain
attacks (xz-utils, polyfill.io) accelerated adoption.

## SLSA levels

```
SLSA L0: No guarantees
  → No provenance, no build integrity
  → Default state for most projects

SLSA L1: Provenance exists
  → Build process documented
  → Provenance metadata generated (who, when, how)
  → Not necessarily verified or tamper-proof

SLSA L2: Hosted build, signed provenance
  → Build runs on a hosted service (CI/CD)
  → Provenance is signed and tamper-resistant
  → Consumers can verify provenance signature

SLSA L3: Hardened build (target for most orgs)
  → Build runs in an isolated, ephemeral environment
  → Build service is trusted (GitHub Actions, Google Cloud Build)
  → Provenance is non-forgeable (the build service signs it)
  → Source integrity: build inputs match declared source

SLSA L4: Hermetic, reproducible
  → Build is fully hermetic (no network access)
  → Reproducible: same source → same artifact
  → Two-party review of source changes
  → Highest integrity guarantee
```

## Sigstore components

```
Cosign:
  → Sign and verify container images and blobs
  → Keyless signing with OIDC identity
  → "cosign sign" attaches signature to OCI registry
  → "cosign verify" checks signature and identity

Fulcio:
  → Certificate authority for ephemeral signing certificates
  → Issues short-lived certs tied to OIDC identity
  → No long-lived signing keys to manage or rotate

Rekor:
  → Transparency log (immutable, append-only)
  → Records all signing events
  → Public audit trail: anyone can verify
  → Detect if a key was compromised retroactively

Gitsign:
  → Sign git commits with Sigstore (keyless)
  → Replaces GPG key management for commit signing
```

## Implementation

### Container image signing (Cosign)

```bash
# Sign a container image (keyless, OIDC)
cosign sign ghcr.io/myorg/myapp:v1.2.3

# Opens browser for OIDC authentication
# Certificate issued by Fulcio
# Signing event recorded in Rekor
# Signature attached to OCI registry

# Verify the image
cosign verify ghcr.io/myorg/myapp:v1.2.3 \
  --certificate-identity=ci@myorg.com \
  --certificate-oidc-issuer=https://token.actions.githubusercontent.com

# Verify with policy (who can sign what)
cosign verify ghcr.io/myorg/myapp:v1.2.3 \
  --certificate-identity-regexp='^https://github.com/myorg/.*' \
  --certificate-oidc-issuer=https://token.actions.githubusercontent.com
```

### GitHub Actions SLSA L3 provenance

```yaml
name: Release
on:
  push:
    tags: ['v*']

jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      digest: ${{ steps.build.outputs.digest }}
    steps:
      - uses: actions/checkout@v4
      - id: build
        run: |
          docker build -t ghcr.io/myorg/myapp:${{ github.ref_name }} .
          docker push ghcr.io/myorg/myapp:${{ github.ref_name }}

  # SLSA L3 provenance generator
  provenance:
    needs: build
    permissions:
      id-token: write    # For Sigstore signing
      contents: read
      packages: write
    uses: slsa-framework/slsa-github-generator/.github/workflows/generator_container_slsa3.yml@v2.1.0
    with:
      image: ghcr.io/myorg/myapp
      digest: ${{ needs.build.outputs.digest }}
    secrets:
      registry-username: ${{ github.actor }}
      registry-password: ${{ secrets.GITHUB_TOKEN }}
```

### npm package provenance

```yaml
# GitHub Actions: publish npm package with provenance
- name: Publish
  run: npm publish --provenance
  env:
    NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}

# npm now displays provenance badge on npmjs.com:
# "Published with provenance from GitHub Actions"
# Links to exact commit, workflow, and build log
```

### Admission control (Kubernetes)

```yaml
# Sigstore policy-controller: only allow signed images
apiVersion: policy.sigstore.dev/v1beta1
kind: ClusterImagePolicy
metadata:
  name: require-signatures
spec:
  images:
    - glob: "ghcr.io/myorg/**"
  authorities:
    - keyless:
        identities:
          - issuer: https://token.actions.githubusercontent.com
            subjectRegExp: "^https://github.com/myorg/.*"
```

## Dependency verification

```
npm:
  → package-lock.json with integrity hashes (SHA-512)
  → npm audit for known vulnerabilities
  → npm provenance verification (npm >= 9.5)

Go:
  → go.sum file with cryptographic hashes
  → GONOSUMCHECK for private modules only
  → sumdb.golang.org for public module verification

Python:
  → pip install --require-hashes
  → pip-audit for vulnerability scanning
  → PEP 740: attestations on PyPI

Container images:
  → Pin by digest, not tag (@sha256:abc123...)
  → Verify Sigstore signatures before deploy
  → Scan with Trivy, Grype, or Snyk
```

## Anti-patterns

- **Pinning tags instead of digests** — using `node:22` instead of
  `node@sha256:abc123...` in Dockerfiles. Tags are mutable — a
  compromised registry can change what a tag points to. Digests are
  immutable content-addressable hashes.
- **Signing with long-lived keys** — managing GPG or PGP keys for
  artifact signing. Keys must be rotated, stored securely, and
  revoked if compromised. Use Sigstore's keyless signing (ephemeral
  certificates tied to CI identity) instead.
- **No provenance for internal artifacts** — only verifying external
  dependencies but not your own build outputs. Internal artifacts
  can be tampered with by compromised CI runners. Generate and
  verify provenance for all artifacts.
- **Audit-only mode forever** — enabling dependency scanning in
  audit mode but never enforcing it. Vulnerabilities accumulate
  without remediation. Set policies that block deployment of
  artifacts with critical vulnerabilities.

## Gotchas

- **SLSA provenance does not guarantee code quality** — SLSA verifies
  that the artifact was built from the declared source by a trusted
  builder. It does not verify that the source code itself is
  correct, secure, or free of vulnerabilities. Complement with
  code review and security scanning.
- **Sigstore certificate expiry** — Sigstore certificates are
  short-lived (10-20 minutes). Verification checks the Rekor
  transparency log to confirm the signature was created while the
  certificate was valid. Offline verification requires the Rekor
  log entry.
- **Private registry signing** — Cosign attaches signatures to OCI
  registries. If your registry does not support OCI artifacts
  (older registries), signatures cannot be stored alongside images.
  Use a registry that supports OCI 1.1+.
- **Build reproducibility is hard** — SLSA L4 requires reproducible
  builds. Most build systems include timestamps, random values, or
  environment-dependent outputs that prevent bit-for-bit
  reproducibility. Achieving L4 requires significant build tooling
  investment.

## Verification

- Container images are signed with Cosign (keyless/Sigstore).
- SLSA L3 provenance is generated for all release artifacts.
- Kubernetes admission control rejects unsigned images.
- Dependencies are pinned by digest/hash, not mutable tags.
- npm/PyPI packages are published with provenance attestations.
- Dependency vulnerabilities are scanned and remediated.
- Signing events are recorded in the Rekor transparency log.

## Related

- `documentation/docs/policies/security/zero-trust-network-architecture-ztna.md`
- `documentation/docs/policies/github/composite-actions-reusable-workflows.md`
- `documentation/docs/policies/devtools/sbom-generation-tools.md`

## Source URLs (verified 2026-08-16)

- SLSA Framework: Supply Chain Levels for Software Artifacts — https://slsa.dev/
- Sigstore: Software Signing for Everyone — https://www.sigstore.dev/
- Software Supply Chain Security Best Practices 2026 — https://snyk.io/series/software-supply-chain-security/
- SLSA and Sigstore in Practice: GitHub Actions Guide — https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations
