# supply-chain-security-sbom-signing

**Issue:** Software supply chain attacks (SolarWinds, dependency confusion, malicious base images) — a 2026 dev team must prove every image is built from known sources, signed, and verifiable
**Date:** 2026-08-12
**Status:** documented

## Symptom
You build a Docker image in CI and push it to a registry. An
attacker compromises a dependency, a base image, or the CI runner
itself. Your pipeline happily builds and deploys the tampered image.
Production runs malicious code. You cannot prove what was in the
image or who built it.

## Root cause
**No artifact attestation.** Without an SBOM (Software Bill of
Materials), image signatures, and provenance metadata, there is no
verifiable chain of trust from source to production.

**Source:** SLSA (Supply-chain Levels for Software Artifacts)
framework, Sigstore/Cosign, OpenSSF. US Executive Order 14028
mandates SBOMs for government software; enterprise customers now
require the same.

## The "generate SBOM" pattern

Generate an SBOM at build time using Syft:

```bash
# Generate SBOM from a Docker image (CycloneDX format)
syft registry.example.com/api:v1.2.0 -o cyclonedx-json > sbom.json

# Or SPDX format
syft registry.example.com/api:v1.2.0 -o spdx-json > sbom.spdx.json

# Generate from source during build
syft dir:. -o cyclonedx-json > sbom.json
```

Attach the SBOM to the image as an attestation:
```bash
cosign attest --predicate sbom.json \
  --type cyclonedx \
  registry.example.com/api:v1.2.0
```

The SBOM is now stored alongside the image in the registry.

## The "sign the image" pattern

Sign with Cosign (keyless, using OIDC from CI):

```bash
# Keyless signing (recommended for CI — uses GitHub/GitLab OIDC)
cosign sign --yes registry.example.com/api:v1.2.0

# Verify the signature before deploy
cosign verify \
  --certificate-identity-regexp "https://github.com/myorg/.*" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  registry.example.com/api:v1.2.0
```

For the GitHub Actions pipeline:
```yaml
# .github/workflows/build-and-sign.yml
name: build-sign-deploy
on:
  push:
    tags: ['v*']
permissions:
  contents: read
  packages: write
  id-token: write   # required for keyless cosign

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/build-push-action@v6
        id: build
        with:
          push: true
          tags: ghcr.io/${{ github.repository }}:${{ github.ref_name }}
      - name: Generate SBOM
        run: |
          curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh
          syft ghcr.io/${{ github.repository }}:${{ github.ref_name }} -o cyclonedx-json > sbom.json
      - name: Sign image (keyless)
        uses: sigstore/cosign-installer@v3
      - run: |
          cosign sign --yes ghcr.io/${{ github.repository }}:${{ github.ref_name }}
          cosign attest --yes --predicate sbom.json --type cyclonedx \
            ghcr.io/${{ github.repository }}:${{ github.ref_name }}
```

## The "enforce at deploy time" pattern

Block unsigned images with Kyverno (admission controller):

```yaml
# kyverno-policy: require-signature.yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: require-signed-images
spec:
  validationFailureAction: Enforce
  rules:
    - name: check-signature
      match:
        any:
          - resources:
              kinds: [Pod]
      verifyImages:
        - imageReferences:
            - "ghcr.io/myorg/*"
          attestors:
            - entries:
                - keyless:
                    subject: "https://github.com/myorg/*"
                    issuer: "https://token.actions.githubusercontent.com"
```

Unsigned images are rejected at admission. Pods never start.

## The "SLSA level" checklist

| Level | Requirement |
|-------|-------------|
| SLSA 1 | Build documented, provenance available |
| SLSA 2 | Hosted build service, signed provenance |
| SLSA 3 | Hardened build platform, isolated builds |
| SLSA 4 | Two-party review, reproducible builds |

Most teams should target SLSA 3 by end of 2026.

## Verification
- **SBOM exists:** `cosign verify-attestation --type cyclonedx <image>`
- **Signature valid:** `cosign verify <image>` exits 0
- **Policy enforced:** `kubectl run test --image=unsigned-image` is
  rejected with `disallowed by admission controller`
- **Dependency scan:** `grype sbom.json` finds no critical CVEs

## Gotchas
- **Keyless signing requires OIDC.** Local `cosign sign` without a
  key needs an OIDC token from CI. For manual/air-gapped signing,
  generate a keypair: `cosign generate-key-pair`.
- **SBOMs for interpreted languages miss runtime deps.** A Node.js
  image's SBOM lists `node_modules`, but if your app dynamically
  `require()`s at runtime, those may not appear. Use `syft dir:.`
  on source, not just the image.
- **Attestations are separate from signatures.** Signing proves
  authenticity; attesting proves properties (SBOM, provenance, vuln
  scan). You need both. `cosign attest` creates a separate signature
  over the predicate — verify it with
  `cosign verify-attestation`.
- **Cosign v2 changed flags.** `cosign sign` no longer needs `--key`
  for keyless; v1 syntax will break. Pin cosign version in CI.
- **Rekor transparency log.** Keyless signatures are recorded in
  Rekor (a public append-only log). If your compliance team requires
  private signatures, use a static key and skip Rekor with
  `--tlog-upload=false`.
- **Cross-registry attestation.** Cosign stores attestations in the
  same registry as the image. If you copy images between registries
  (dev → prod), re-sign and re-attest in the destination, or use
  `cosign copy` which preserves signatures.

## Related
- `docker-security-scanning.md`
- `container-image-tagging.md`
- `kubernetes-rbac-patterns.md`
- `gitops-secrets-management.md`
- Sigstore: https://www.sigstore.dev/
- SLSA framework: https://slsa.dev/
- Syft: https://github.com/anchore/syft
